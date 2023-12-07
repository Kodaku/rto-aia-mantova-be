from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import random
from supabase import create_client, Client
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from pathlib import Path
import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta

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
    header = {"alg": "HS256", "typ": "JWT"}
    # Payload data
    payload = {
        "exp": int((datetime.utcnow() + timedelta(seconds=JWT_EXPIRATION_TIME)).timestamp()),  # Expiration time
        "codiceMeccanografico": mechanographic_code,
    }

    encoded_header = base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode()).decode()
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()

    # Combine the encoded header and payload with a period '.'
    encoded_token = f"{encoded_header}.{encoded_payload}"

    # Sign the token with the secret key using HMAC-SHA256
    signature = hmac.new(JWT_SECRET_KEY.encode(), encoded_token.encode(), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode()

    # Combine the token and signature with a period '.'
    jwt_token = f"{encoded_token}.{encoded_signature}"
    # expiration_time = datetime.utcnow() + timedelta(seconds=JWT_EXPIRATION_TIME)
    # payload = {
    #     "codiceMeccanografico": mechanographic_code,
    #     "exp": expiration_time,
    # }
    # token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return jwt_token

def decode_jwt(jwt_token, secret_key):
    try:
        # Split the token into its parts (header, payload, and signature)
        encoded_header, encoded_payload, signature = jwt_token.split(".")

        # Decode the header and payload from Base64 URL-safe strings
        header = json.loads(base64.urlsafe_b64decode(encoded_header.encode()).decode())
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode()).decode())

        # Verify the signature by re-signing the header and payload
        re_signature = hmac.new(secret_key.encode(), f"{encoded_header}.{encoded_payload}".encode(), hashlib.sha256).digest()
        re_encoded_signature = base64.urlsafe_b64encode(re_signature).decode()

        if re_encoded_signature != signature:
            return None  # Signature verification failed

        return payload
    except (ValueError, json.JSONDecodeError, KeyError):
        return None  # Invalid token or payload
    
    

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    payload = decode_jwt(token, JWT_SECRET_KEY)
    # print(payload)
    # payload = json.dumps(payload)
    print(payload)
    # payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
    expiration_time = datetime.fromtimestamp(payload["exp"])
    if datetime.utcnow() > expiration_time:
        raise HTTPException(status_code=401, detail="Token has expired")
    return payload
    


@app.get("/giustifiche")
async def read_root():
    # Assuming "index.html" is your main HTML file in the React build
    html_path = Path("build/index.html")
    return FileResponse(html_path)

@app.get("/")
async def read_root():
    # Assuming "index.html" is your main HTML file in the React build
    html_path = Path("build/presenze.html")
    return FileResponse(html_path)

@app.get("/verify")
async def veriy_me(payload: dict = Depends(verify_token)):
    return {"codiceMeccanografico": payload.get("codiceMeccanografico")}


@app.get("/users")
async def find_all_users():
    users = supabase.table(USER_TABLE).select("*").execute()
    return users.data


@app.get("/users/{codiceMeccanografico}")
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


@app.post("/users")
async def create_user(user: User):
    user = {"codiceMeccanografico": user.codiceMeccanografico, "nome": user.nome, "cognome": user.cognome,
            "email": user.email, "codiceCategoria": user.codiceCategoria, "categoriaEstesa": user.categoriaEstesa,
            "qualifica": user.qualifica, "selezionabile": user.selezionabile}
    data, _ = supabase.table(USER_TABLE).upsert(user).execute()
    return data

@app.get("/users/delete/{codiceMeccanografico}")
async def delete_user_by_code(codiceMeccanografico: str, payload: dict = Depends(verify_token)):
    data = supabase.table(USER_TABLE).delete().eq("codiceMeccanografico", codiceMeccanografico)
    return {"msg": "Deleted"}


@app.post("/rtos")
async def create_rto(rto: RTO):
    # Create the qrcode for the rto
    users = supabase.table(USER_TABLE).select("*").execute().data
    qrcodes = {}
    for user in users:
        qrcode = str(random.randint(0, 99999)).zfill(5)
        qrcodes[user["codiceMeccanografico"]] = qrcode
    rto = {"dataRTO": rto.dataRTO, "descrizione": rto.descrizione, "qrcodes": qrcodes,
            "codiciCategoria": rto.codiciCategoria, "categorieEstese": rto.categorieEstese}
    data, _ = supabase.table(RTO_TABLE).upsert(rto).execute()
    print(data[1][0])
    return data[1][0]


@app.post("/rtos/users/{rto_date}")
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

@app.get("/rtos/justifications/{codiceMeccanografico}")
async def get_justifications_of_user(codiceMeccanografico: int):
    giustifiche = supabase.table(LINK_USER_RTO).select("dataRTO, statoUtente, descrizioneGiustifica, motivo")\
                                                .eq("codiceMeccanografico", codiceMeccanografico)\
                                                .execute()
    print(giustifiche.data)
    return giustifiche.data

@app.post("/rtos/justifications/{rto_date}")
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


@app.get("/rtos")
async def find_all_rtos():
    rtos = supabase.table(RTO_TABLE).select("*").execute()
    return rtos.data


@app.get("/rtos/{rto_date}")
async def find_rto_by_date(rto_date: str, payload: dict = Depends(verify_token)):
    rto = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute()
    print(rto.data)
    return rto.data

@app.get("/rtos/{rto_date}/{codiceMeccanografico}/{qrcode}")
async def find_rto_by_qrcode(rto_date: str, codiceMeccanografico: int, qrcode: str, payload: dict = Depends(verify_token)):
    rto = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute().data[0]
    print(rto)
    found = False
    if rto is not None:
        qrcodes = rto['qrcodes']
        if str(codiceMeccanografico) in qrcodes:
            print("Codice meccanografico presente")
            if qrcodes[str(codiceMeccanografico)] == qrcode:
                found = True
    if found:
        return rto
    return None


@app.get("/rtos/delete/{rto_date}")
async def delete_rto_by_date(rto_date: str):
    rto_to_delete = supabase.table(RTO_TABLE).select("*").eq("dataRTO", rto_date).execute()
    if len(rto_to_delete.data) > 0:
        links_deleted = supabase.table(LINK_USER_RTO).delete().eq("dataRTO", rto_to_delete.data[0]["dataRTO"]).execute()
        data = supabase.table(RTO_TABLE).delete().eq("dataRTO", rto_date).execute()
        print(data, links_deleted)
        return {"msg": "Deleted"}
    return {"msg": "RTO to delete does not exist"}


@app.get("/rtos/delete/user/{rto_date}/{codiceMeccanografico}")
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
