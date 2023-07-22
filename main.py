import json

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
from elasticsearch import Elasticsearch, RequestError
from es_search import find_all, find_by_name
from fastapi.middleware.cors import CORSMiddleware
import random

JWT_SECRET_KEY = "5dd4e8585d1323d9d8e2a9d6f88c6ef319e1b52a2472e5baf0d3c18398ae9f2a"
JWT_EXPIRATION_TIME = 2 * 60 * 60  # 2 hours in seconds


class User(BaseModel):
    name: str
    surname: str
    mechanographicCode: str

class AuthenticatedUser:
    name: str
    surname: str
    mechanographicCode: str
    token: str

class RTOJustification(BaseModel):
    motivation: str
    motivation_description: str
    user: User


class RTO(BaseModel):
    date: str
    description: str
    users: list
    justifications: list
    qrcode: str


es = Elasticsearch(
    hosts=['http://localhost:9200'],
    basic_auth=('elastic', 'e0_kX+xT1Oh_v+8pLot3')
)


def es_create_index_if_not_exists(es, index):
    try:
        es.indices.create(index=index)
    except RequestError as ex:
        print(ex)

app = FastAPI()
security = HTTPBearer()

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_jwt_token(mechanographic_code: str) -> str:
    expiration_time = datetime.utcnow() + timedelta(seconds=JWT_EXPIRATION_TIME)
    payload = {
        "mechanographicCode": mechanographic_code,
        "exp": expiration_time,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return token

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        expiration_time = datetime.fromtimestamp(payload["exp"])
        if datetime.utcnow() > expiration_time:
            raise HTTPException(status_code=401, detail="Token has expired")
        return payload
    except (jwt.DecodeError, jwt.ExpiredSignatureError):
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/")
async def test_endpoint():
    return {"message": "Hello!"}

@app.get("/verify")
async def veriy_me(payload: dict = Depends(verify_token)):
    print({"mechanographicCode": payload.get("mechanographicCode")})
    return {"mechanographicCode": payload.get("mechanographicCode")}


@app.get("/users")
async def find_all_users():
    users = find_all(es, "aia_mn_users")
    return users


@app.get("/users/{mechanographicCode}")
async def find_user_by_name(mechanographicCode: str):
    user = find_by_name(es, "aia_mn_users", "mechanographicCode", mechanographicCode)
    if user is not None:
        token = generate_jwt_token(mechanographicCode)
        response = AuthenticatedUser()
        response.name = user["name"]
        response.surname = user["surname"]
        response.mechanographicCode = user["mechanographicCode"]
        response.token = token
        return response
    return None


@app.post("/users")
async def create_user(user: User):
    if not es.indices.exists(index="aia_mn_users"):
        print(f"Index users created")
        es_create_index_if_not_exists(es, "aia_mn_users")
    actions = []
    action = {"index": {"_index": "aia_mn_users", "_id": user.mechanographicCode}, "_op_type": "upsert"}
    user = {"mechanographicCode": user.mechanographicCode, "name": user.name, "surname": user.surname}
    doc = json.dumps(user)
    actions.append(action)
    actions.append(doc)
    res = es.bulk(index="aia_mn_users", operations=actions)
    print(res)
    return user

@app.get("/users/delete/{mechanographicCode}")
async def delete_user_by_code(mechanographicCode: str, payload: dict = Depends(verify_token)):
    es.delete(index="aia_mn_users", id=mechanographicCode)
    return {"msg": "Deleted"}


@app.post("/rtos")
async def create_rto(rto: RTO):
    if not es.indices.exists(index="rtos"):
        print(f"Index rtos created")
        es_create_index_if_not_exists(es, "rtos")
    actions = []
    action = {"index": {"_index": "rtos", "_id": rto.date}, "_op_type": "upsert"}
    # Create the qrcode for the rto
    qrcode = str(random.randint(0, 99999)).zfill(5)
    rto = {"date": rto.date, "description": rto.description, "users": [], "justifications": [], "qrcode": qrcode}
    doc = json.dumps(rto)
    actions.append(action)
    actions.append(doc)
    res = es.bulk(index="rtos", operations=actions)
    print(res)
    return rto


@app.post("/rtos/users/{rto_date}")
async def add_user_to_rto(rto_date: str, user: User, payload: dict = Depends(verify_token)):
    rto = find_by_name(es, "rtos", "date", rto_date)
    users = rto['users']
    print(users)
    user = {"name": user.name, "surname": user.surname, "mechanographicCode": user.mechanographicCode}
    found = False
    for rtoUser in users:
        if user["mechanographicCode"] == rtoUser["mechanographicCode"]:
            found = True
    if not found:
        users.append(user)
    else:
        print(f"The user {user['name']} is already registered to this RTO")
    actions = []
    action = {"index": {"_index": "rtos", "_id": rto["date"]}, "_op_type": "upsert"}
    rto = {"date": rto["date"], "description": rto["description"], "users": users, "justifications": rto["justifications"],
            "qrcode": rto["qrcode"]}
    doc = json.dumps(rto)
    actions.append(action)
    actions.append(doc)
    res = es.bulk(index="rtos", operations=actions)
    print(res)
    return find_by_name(es, "rtos", "date", rto_date)

@app.post("/rtos/justifications/{rto_date}")
async def add_justification_to_rto(rto_date: str, rto_justification: RTOJustification, payload: dict = Depends(verify_token)):
    rto = find_by_name(es, "rtos", "date", rto_date)
    justifications = rto['justifications']
    print(rto_justification)
    user = rto_justification.user
    user = {"name": user.name, "surname": user.surname, "mechanographicCode": user.mechanographicCode}
    justification_user = rto_justification.user
    rto_justification = {"motivation": rto_justification.motivation, "motivation_description": rto_justification.motivation_description,
                        "user": {"name": justification_user.name, "surname": justification_user.surname, "mechanographicCode": justification_user.mechanographicCode}}
    found = False
    for justification in justifications:
        if user["mechanographicCode"] == justification["user"]["mechanographicCode"]:
            found = True
    if not found:
        justifications.append(rto_justification)
    else:
        print(f"The user {user['name']} is already justified to this RTO")
        return None
    actions = []
    action = {"index": {"_index": "rtos", "_id": rto["date"]}, "_op_type": "upsert"}
    rto = {"date": rto["date"], "description": rto["description"], "users": rto["users"], "justifications": justifications,
            "qrcode": rto["qrcode"]}
    doc = json.dumps(rto)
    actions.append(action)
    actions.append(doc)
    res = es.bulk(index="rtos", operations=actions)
    print(res)
    return find_by_name(es, "rtos", "date", rto_date)


@app.get("/rtos")
async def find_all_rtos():
    if es.indices.exists(index="rtos"):
        rtos = find_all(es, "rtos")
        return rtos
    return {"error": "index rtos does not exist"}


@app.get("/rtos/{rto_date}")
async def find_rto_by_date(rto_date: str, payload: dict = Depends(verify_token)):
    rto = find_by_name(es, "rtos", "date", rto_date)
    return rto

@app.get("/rtos/{qrcode}")
async def find_rto_by_qrcode(qrcode: str, payload: dict = Depends(verify_token)):
    rto = find_by_name(es, "rtos", "qrcode", qrcode)
    return rto


@app.get("/rtos/delete/{rto_date}")
async def delete_wish_list_by_name(rto_date: str):
    es.delete(index="rtos", id=rto_date)
    return {"msg": "Deleted"}


@app.get("/rtos/delete/user/{rto_date}/{mechanographicCode}")
async def delete_user_from_list(rto_date: str, mechanographicCode: str):
    rto = find_by_name(es, "rtos", "date", rto_date)
    users = rto['users']
    for user in users:
        if user["mechanographicCode"] == mechanographicCode:
            print(user)
            users.remove(user)
            break
    actions = []
    action = {"index": {"_index": "rtos", "_id": rto_date}, "_op_type": "upsert"}
    rto = {"date": rto["date"], "description": rto["description"], "users": users, "justifications": rto["justifications"],
            "qrcode": rto["qrcode"]}
    doc = json.dumps(rto)
    actions.append(action)
    actions.append(doc)
    res = es.bulk(index="rtos", operations=actions)
    print(res)
    return find_by_name(es, "rtos", "date", rto_date)
