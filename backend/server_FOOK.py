# -*- coding: utf-8 -*-
from __future__ import annotations
import os, random, uuid
from datetime import date
from typing import Optional, Any
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from database import db
from auth_utils import hash_password, verify_password, issue_session, resolve_user

app = FastAPI(title='FOOK 통합 API', version='9.0.0')
origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

class SignupReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=60)
class LoginReq(BaseModel):
    email: EmailStr
    password: str
class ProfileReq(BaseModel):
    gender: Optional[str]=None
    age: Optional[int]=Field(default=None, ge=1, le=120)
    height: Optional[float]=Field(default=None, ge=50, le=250)
    weight: Optional[float]=Field(default=None, ge=20, le=300)
    dialysis: str='혈액투석'
class GenReq(BaseModel):
    menu: Optional[str]=None
    ingredient: Optional[str]=None
    weight: int=60
    consumed: Optional[dict]=None
    meals_left: int=3
class DayReq(BaseModel):
    weight: int=60
    menus: Optional[list]=None
    ingredients: Optional[list]=None
class SaveReq(BaseModel):
    title: str
    subtitle: Optional[str]=None
    payload: dict={}
class CartReq(BaseModel):
    name: str
    amount: Optional[float]=None
    unit: str='g'
    checked: bool=False


def bearer(authorization: Optional[str]=Header(default=None)):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401,'로그인이 필요합니다.')
    token=authorization.split(' ',1)[1].strip()
    with db() as conn:
        user=resolve_user(conn,token)
    if not user: raise HTTPException(401,'로그인이 만료되었습니다.')
    return dict(user)

@app.get("/health")
def health():
    try:
        with db() as conn:
            conn.execute(text("select 1"))
            menus = conn.execute(text("select count(*) from menus")).scalar_one()
            templates = conn.execute(
                text("select count(distinct (day_number, meal_type)) from diet_calendar")
            ).scalar_one()

        return {
            "ok": True,
            "version": "9.0.0",
            "data_source": "neon",
            "menus": menus,
            "meal_templates": templates,
            "auth": "database",
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "error": type(e).__name__,
            "message": str(e),
        }

@app.post('/auth/signup',status_code=201)
def signup(req:SignupReq):
    email=req.email.lower().strip()
    with db() as conn:
        if conn.execute(text('select 1 from app_users where lower(email)=:e'),{'e':email}).first():
            raise HTTPException(409,'이미 가입된 이메일입니다.')
        uid=str(uuid.uuid4())
        conn.execute(text('insert into app_users(id,email,password_hash,display_name) values(:i,:e,:p,:n)'),{'i':uid,'e':email,'p':hash_password(req.password),'n':req.name.strip()})
        conn.execute(text('insert into user_profiles(user_id,dialysis_type) values(:u,\'혈액투석\')'),{'u':uid})
        token=issue_session(conn,uid)
    return {'token':token,'user':{'id':uid,'email':email,'name':req.name.strip()}}

@app.post('/auth/login')
def login(req:LoginReq):
    with db() as conn:
        row=conn.execute(text('select id,email,password_hash,display_name,is_active from app_users where lower(email)=:e'),{'e':req.email.lower().strip()}).mappings().first()
        if not row or not row['is_active'] or not verify_password(req.password,row['password_hash']):
            raise HTTPException(401,'이메일 또는 비밀번호가 올바르지 않습니다.')
        conn.execute(text('update app_users set last_login_at=now() where id=:i'),{'i':row['id']})
        token=issue_session(conn,str(row['id']))
    return {'token':token,'user':{'id':str(row['id']),'email':row['email'],'name':row['display_name']}}

@app.post('/auth/logout',status_code=204)
def logout(authorization:Optional[str]=Header(default=None)):
    if authorization and authorization.lower().startswith('bearer '):
        import hashlib
        h=hashlib.sha256(authorization.split(' ',1)[1].strip().encode()).hexdigest()
        with db() as conn: conn.execute(text('update auth_sessions set revoked_at=now() where token_hash=:h'),{'h':h})

@app.get('/me')
def me(user=Depends(bearer)):
    with db() as conn:
        p=conn.execute(text('select gender,age,height_cm,weight_kg,dialysis_type from user_profiles where user_id=:u'),{'u':user['id']}).mappings().first()
    return {'user':{'id':str(user['id']),'email':user['email'],'name':user['display_name']},'profile':dict(p) if p else None}

@app.put('/me/profile')
def update_profile(req:ProfileReq,user=Depends(bearer)):
    with db() as conn:
        conn.execute(text('''insert into user_profiles(user_id,gender,age,height_cm,weight_kg,dialysis_type)
        values(:u,:g,:a,:h,:w,:d) on conflict(user_id) do update set gender=excluded.gender,age=excluded.age,height_cm=excluded.height_cm,weight_kg=excluded.weight_kg,dialysis_type=excluded.dialysis_type,updated_at=now()'''),
        {'u':user['id'],'g':req.gender,'a':req.age,'h':req.height,'w':req.weight,'d':req.dialysis})
    return {'ok':True}

@app.get('/menus')
def menus(q:Optional[str]=None):
    with db() as conn:
        if q: rows=conn.execute(text('select name from menus where name ilike :q order by name limit 100'),{'q':f'%{q}%'}).scalars().all()
        else: rows=conn.execute(text('select name from menus order by name limit 3000')).scalars().all()
    return {'menus':rows}

@app.get('/ingredients')
def ingredients(q:Optional[str]=None):
    sql='select distinct ingredient_name_raw from menu_ingredients where ingredient_name_raw is not null'
    params={}
    if q: sql+=' and ingredient_name_raw ilike :q';params['q']=f'%{q}%'
    sql+=' order by ingredient_name_raw limit 3000'
    with db() as conn: rows=conn.execute(text(sql),params).scalars().all()
    return {'ingredients':rows}

def pick_meal(conn, menu=None, ingredient=None):
    anchor=menu
    if ingredient and not anchor:
        anchor=conn.execute(text('''select m.name from menu_ingredients mi join menus m on m.id=mi.menu_id where mi.ingredient_name_raw ilike :q order by random() limit 1'''),{'q':f'%{ingredient}%'}).scalar()
    if anchor:
        day=conn.execute(text('''select dc.day_number,dc.meal_type from diet_calendar dc join menus m on m.id=dc.menu_id where m.name=:n order by random() limit 1'''),{'n':anchor}).mappings().first()
    else: day=None
    if not day:
        day=conn.execute(text('select day_number,meal_type from diet_calendar group by day_number,meal_type order by random() limit 1')).mappings().first()
    if not day: raise HTTPException(503,'diet_calendar에 식단 데이터가 없습니다.')
    rows=conn.execute(text('''select dc.slot_index,m.name,coalesce(m.energy,0) energy,coalesce(m.protein,0) protein,coalesce(m.potassium,0) potassium,coalesce(m.phosphorus,0) phosphorus,coalesce(m.sodium,0) sodium from diet_calendar dc join menus m on m.id=dc.menu_id where dc.day_number=:d and dc.meal_type=:t order by dc.slot_index'''),{'d':day['day_number'],'t':day['meal_type']}).mappings().all()
    return rows,anchor

@app.post('/generate')
def generate(req:GenReq):
    with db() as conn:
        rows,anchor=pick_meal(conn,req.menu,req.ingredient)
        meal=[r['name'] for r in rows]
        nutrition={'energy':sum(float(r['energy']) for r in rows),'protein':sum(float(r['protein']) for r in rows),'potassium':sum(float(r['potassium']) for r in rows),'phosphorus':sum(float(r['phosphorus']) for r in rows),'sodium':sum(float(r['sodium']) for r in rows)}
        dish={}
        for name in meal:
            ings=conn.execute(text('''select ingredient_name_raw,coalesce(amount_g,0) amount_g from menu_ingredients mi join menus m on m.id=mi.menu_id where m.name=:n order by coalesce(sort_order,0)'''),{'n':name}).all()
            dish[name]=[[x[0],float(x[1])] for x in ings]
    targets={'energy':550,'protein':24,'potassium':1200,'phosphorus':550,'sodium':400}
    passed=nutrition['potassium']<=targets['potassium'] and nutrition['phosphorus']<=targets['phosphorus'] and nutrition['sodium']<=targets['sodium']
    return {'meal':meal,'nutrition':nutrition,'targets':targets,'passed':passed,'note':f'Neon 식단 템플릿 기반 추천'+(f' · {anchor} 포함' if anchor else ''),'warning':None if passed else '일부 영양소가 권장 목표를 초과할 수 있어 의료진과 상의하세요.','changes':[],'dish_ingredients':dish,'snacks':[],'recipe_source':anchor,'anchor':anchor,'mode':'neon-template','intake':{'E':nutrition['energy'],'protein':nutrition['protein'],'K':nutrition['potassium'],'P':nutrition['phosphorus'],'Na':nutrition['sodium'],'Na_season':nutrition['sodium']}}

@app.post('/generate_day')
def generate_day(req:DayReq):
    return {'meals':[generate(GenReq(weight=req.weight,menu=(req.menus or [None]*3)[i] if i<len(req.menus or []) else None,ingredient=(req.ingredients or [None]*3)[i] if i<len(req.ingredients or []) else None)) for i in range(3)]}

@app.post('/recipe')
def recipe(payload:dict):
    return {'menu':payload.get('menu'),'steps':['재료를 필요한 크기로 손질합니다.','나트륨 사용을 줄이고 재료 본연의 맛을 살려 조리합니다.','충분히 익힌 뒤 1회 제공량에 맞춰 담습니다.']}

# 개인 데이터 공통 API
RESOURCE_TABLES={'meal-records':'meal_records','favorites':'favorites','documents':'user_documents'}
@app.get('/me/{resource}')
def list_resource(resource:str,user=Depends(bearer)):
    table=RESOURCE_TABLES.get(resource)
    if not table: raise HTTPException(404)
    with db() as conn: rows=conn.execute(text(f'select id,title,subtitle,payload,created_at from {table} where user_id=:u order by created_at desc'),{'u':user['id']}).mappings().all()
    return {'items':[dict(r) for r in rows]}
@app.post('/me/{resource}',status_code=201)
def save_resource(resource:str,req:SaveReq,user=Depends(bearer)):
    table=RESOURCE_TABLES.get(resource)
    if not table: raise HTTPException(404)
    rid=str(uuid.uuid4())
    with db() as conn: conn.execute(text(f'insert into {table}(id,user_id,title,subtitle,payload) values(:i,:u,:t,:s,:p)'),{'i':rid,'u':user['id'],'t':req.title,'s':req.subtitle,'p':req.payload})
    return {'id':rid}
@app.delete('/me/{resource}/{item_id}',status_code=204)
def delete_resource(resource:str,item_id:str,user=Depends(bearer)):
    table=RESOURCE_TABLES.get(resource)
    if not table: raise HTTPException(404)
    with db() as conn: conn.execute(text(f'delete from {table} where id=:i and user_id=:u'),{'i':item_id,'u':user['id']})

@app.get('/me/cart')
def get_cart(user=Depends(bearer)):
    with db() as conn: rows=conn.execute(text('select id,name,amount,unit,checked from shopping_cart_items where user_id=:u order by created_at'),{'u':user['id']}).mappings().all()
    return {'items':[dict(r) for r in rows]}
@app.post('/me/cart',status_code=201)
def add_cart(req:CartReq,user=Depends(bearer)):
    rid=str(uuid.uuid4())
    with db() as conn: conn.execute(text('insert into shopping_cart_items(id,user_id,name,amount,unit,checked) values(:i,:u,:n,:a,:un,:c)'),{'i':rid,'u':user['id'],'n':req.name,'a':req.amount,'un':req.unit,'c':req.checked})
    return {'id':rid}
@app.patch('/me/cart/{item_id}')
def patch_cart(item_id:str,payload:dict,user=Depends(bearer)):
    with db() as conn: conn.execute(text('update shopping_cart_items set checked=coalesce(:c,checked),updated_at=now() where id=:i and user_id=:u'),{'c':payload.get('checked'),'i':item_id,'u':user['id']})
    return {'ok':True}
@app.delete('/me/cart/{item_id}',status_code=204)
def delete_cart(item_id:str,user=Depends(bearer)):
    with db() as conn: conn.execute(text('delete from shopping_cart_items where id=:i and user_id=:u'),{'i':item_id,'u':user['id']})
