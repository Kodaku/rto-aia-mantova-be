from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import random
from supabase import create_client, Client
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from pathlib import Path

JWT_SECRET_KEY = "5dd4e8585d1323d9d8e2a9d6f88c6ef319e1b52a2472e5baf0d3c18398ae9f2a"
JWT_EXPIRATION_TIME = 2 * 60 * 60  # 2 hours in seconds
USER_TABLE = "user_rto"
RTO_TABLE = "rto"
LINK_USER_RTO = "link_user_rto"

supabase: Client = create_client("https://uuazcwidlitcmbusqzii.supabase.co", 
                                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV1YXpjd2lkbGl0Y21idXNxemlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE2OTE3NzA1MzMsImV4cCI6MjAwNzM0NjUzM30.rQoRVUDDEPOJDPeP-K6fNw3o6kJ5X5LUsCQPxqxuo8Q")


class User(BaseModel):
    nome: str
    cognome: str
    codiceMeccanografico: str
    email: str
    codiceCategoria: str
    categoriaEstesa: str
    selezionabile: bool
    qualifica: str


class AuthenticatedUser:
    nome: str
    cognome: str
    codiceMeccanografico: str
    email: str
    codiceCategoria: str
    categoriaEstesa: str
    selezionabile: bool
    qualifica: str
    token: str

class RTOJustification(BaseModel):
    motivation: str
    motivation_description: str
    codiceMeccanografico: str

class RTO(BaseModel):
    dataRTO: str
    descrizione: str
    codiciCategoria: list[str]
    categorieEstese: list[str]

class LinkUserRTO(BaseModel):
    user_id: int
    rto_id: int
    statoUtente: str
    descrizioneGiustifica: str
    motivo: str


app = FastAPI()
security = HTTPBearer()

app.mount("/static", StaticFiles(directory="build/static"), name="build")
app.mount("/bootstrap-italia", StaticFiles(directory="build/bootstrap-italia"), name="bootstrap-italia")

# app.mount("/static", StaticFiles(directory="static/static"), name="static")
# app.mount("/bootstrap-italia2", StaticFiles(directory="static/bootstrap-italia"), name="bootstrap-italia2")

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
        "codiceMeccanografico": mechanographic_code,
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


@app.get("/aia/giustifiche")
async def read_root():
    # Assuming "index.html" is your main HTML file in the React build
    html_path = Path("build/index.html")
    return FileResponse(html_path)

@app.get("/aia")
async def read_root():
    # Assuming "index.html" is your main HTML file in the React build
    html_path = Path("build/presenze.html")
    return FileResponse(html_path)

@app.get("/aia/verify")
async def veriy_me(payload: dict = Depends(verify_token)):
    return {"codiceMeccanografico": payload.get("codiceMeccanografico")}


@app.get("/aia/users")
async def find_all_users():
    users = supabase.table(USER_TABLE).select("*").execute()
    return users.data


@app.get("/aia/users/{codiceMeccanografico}")
async def find_user_by_name(codiceMeccanografico: str):
    user = supabase.table(USER_TABLE).select("*").eq("codiceMeccanografico", codiceMeccanografico).execute().data
    if user is not None:
        user = user[0]
        token = generate_jwt_token(codiceMeccanografico)
        response = AuthenticatedUser()
        response.nome = user["nome"]
        response.cognome = user["cognome"]
        response.codiceMeccanografico = str(user["codiceMeccanografico"])
        response.categoriaEstesa = user['categoriaEstesa']
        response.codiceCategoria = user['codiceCategoria']
        response.email = user['email']
        response.qualifica = user['qualifica']
        response.selezionabile = user['selezionabile']
        response.token = token
        return response
    return None


@app.post("/aia/users")
async def create_user(user: User):
    user = {"codiceMeccanografico": user.codiceMeccanografico, "nome": user.nome, "cognome": user.cognome,
            "email": user.email, "codiceCategoria": user.codiceCategoria, "categoriaEstesa": user.categoriaEstesa,
            "qualifica": user.qualifica, "selezionabile": user.selezionabile}
    data, _ = supabase.table(USER_TABLE).upsert(user).execute()
    return data

@app.get("/aia/users/delete/{codiceMeccanografico}")
async def delete_user_by_code(codiceMeccanografico: str, payload: dict = Depends(verify_token)):
    data = supabase.table(USER_TABLE).delete().eq("codiceMeccanografico", codiceMeccanografico)
    return {"msg": "Deleted"}


@app.post("/aia/rtos")
async def create_rto(rto: RTO):
    # Create the qrcode for the rto
    qrcode = str(random.randint(0, 99999)).zfill(5)
    rto = {"dataRTO": rto.dataRTO, "descrizione": rto.descrizione, "qrcode": qrcode,
            "codiciCategoria": rto.codiciCategoria, "categorieEstese": rto.categorieEstese}
    data, _ = supabase.table(RTO_TABLE).upsert(rto).execute()
    print(data[1][0])
    return data[1][0]


@app.post("/aia/rtos/users/{rto_date}")
async def add_user_to_rto(rto_date: str, user: User, payload: dict = Depends(verify_token)):
    rto = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute().data[0]
    found_user = supabase.table(USER_TABLE).select("*").eq("codiceMeccanografico", user.codiceMeccanografico).execute().data[0]
    print(rto)
    print(found_user)
    response = supabase.table(LINK_USER_RTO).select("*").eq("codiceMeccanografico", found_user['codiceMeccanografico'])\
                                                        .eq("dataRTO", rto['dataRTO']).execute().data
    found = False
    if len(response) > 0:
        found = True
    if found:
        print(f"The user {user['name']} is already registered to this RTO")
        return response
    else:
        data, _ = supabase.table(LINK_USER_RTO)\
                    .upsert({"codiceMeccanografico": found_user['codiceMeccanografico'], "dataRTO": rto['dataRTO'], 
                            "statoUtente":"PRESENTE", "descrizioneGiustifica": "", "motivo": ""})\
                    .execute()
        print(data[0][1])
        return data[0][1]

@app.get("/aia/rtos/justifications/{codiceMeccanografico}")
async def get_justifications_of_user(codiceMeccanografico: int):
    giustifiche = supabase.table(LINK_USER_RTO).select("dataRTO, statoUtente, descrizioneGiustifica, motivo")\
                                                .eq("codiceMeccanografico", codiceMeccanografico)\
                                                .execute()
    print(giustifiche.data)
    return giustifiche.data

@app.post("/aia/rtos/justifications/{rto_date}")
async def add_justification_to_rto(rto_date: str, rto_justification: RTOJustification, payload: dict = Depends(verify_token)):
    rto = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute().data[0]
    found_user = supabase.table(USER_TABLE).select("*").eq("codiceMeccanografico",
                                                            rto_justification.codiceMeccanografico).execute().data[0]
    print(rto)
    print(found_user)
    response = supabase.table(LINK_USER_RTO).select("*").eq("codiceMeccanografico", found_user['codiceMeccanografico'])\
                                            .eq("dataRTO", rto['dataRTO']).execute().data
    if len(response) == 0:
        data, _ = supabase.table(LINK_USER_RTO)\
                    .upsert({"codiceMeccanografico": found_user['codiceMeccanografico'], "dataRTO": rto['dataRTO'],
                            "statoUtente": 'ASSENTE GIUSTIFICATO',
                            "descrizioneGiustifica": rto_justification.motivation_description,
                            'motivo': rto_justification.motivation})\
                    .execute()
        print(data)
        return supabase.table(LINK_USER_RTO).select("dataRTO, statoUtente, descrizioneGiustifica, motivo")\
                                                .eq("codiceMeccanografico", rto_justification.codiceMeccanografico)\
                                                .execute()
    return None


@app.get("/aia/rtos")
async def find_all_rtos():
    rtos = supabase.table(RTO_TABLE).select("*").execute()
    return rtos.data


@app.get("/aia/rtos/{rto_date}")
async def find_rto_by_date(rto_date: str, payload: dict = Depends(verify_token)):
    rto = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute()
    print(rto.data)
    return rto.data

@app.get("/aia/rtos/{qrcode}")
async def find_rto_by_qrcode(qrcode: str, payload: dict = Depends(verify_token)):
    rto = supabase.table(RTO_TABLE).select("*").eq("qrcode", qrcode).execute()
    print(rto)
    return rto


@app.get("/aia/rtos/delete/{rto_date}")
async def delete_rto_by_date(rto_date: str):
    rto_to_delete = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute()
    if len(rto_to_delete.data) > 0:
        links_deleted = supabase.table(LINK_USER_RTO).delete().eq("dataRTO", rto_to_delete.data[0]["dataRTO"]).execute()
        data = supabase.table(RTO_TABLE).delete().eq("dataRTO", rto_date).execute()
        print(data, links_deleted)
        return {"msg": "Deleted"}
    return {"msg": "RTO to delete does not exist"}


@app.get("/aia/rtos/delete/user/{rto_date}/{codiceMeccanografico}")
async def delete_user_from_rto(rto_date: str, codiceMeccanografico: str):
    rto = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute()
    found_user = supabase.table(USER_TABLE).select("*").eq("codiceMeccanografico", codiceMeccanografico).execute()
    query = f"""
    DELETE
    FROM {LINK_USER_RTO}
    WHERE codiceMeccanografico = {found_user.codiceMeccanografico}
        AND dataRTO = {rto.dataRTO}
    """
    response = supabase.sql(query)
    return response
