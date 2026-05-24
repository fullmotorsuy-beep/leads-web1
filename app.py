"""
Gestor de Leads PRO — Version Web para Railway
"""
from flask import Flask, render_template, request, jsonify
import sqlite3, json, os, urllib.parse
from datetime import datetime

try:
    import requests as req
    HAS_REQUESTS = True
except:
    HAS_REQUESTS = False

app = Flask(__name__)
DB = "leads_pro.db"

IGNORAR_ZONA = {
    "argentina","buenos aires","provincia de buenos aires",
    "ciudad autonoma de buenos aires","caba","cordoba","santa fe",
    "mendoza","tucuman","entre rios","salta","misiones","chaco",
    "corrientes","santiago del estero","san juan","jujuy","rio negro",
    "neuquen","formosa","chubut","san luis","catamarca","la rioja",
    "la pampa","santa cruz","tierra del fuego"
}

def extraer_zona(addr):
    if not addr: return ""
    partes = [p.strip() for p in addr.split(",")]
    for p in reversed(partes):
        if p.lower() not in IGNORAR_ZONA and not p.lower().startswith("c.p") and len(p) > 2:
            return p
    return partes[0] if partes else ""

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS clientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        telefono TEXT DEFAULT '',
        direccion TEXT DEFAULT '',
        zona TEXT DEFAULT '',
        rubro TEXT DEFAULT 'Otro',
        estado TEXT DEFAULT 'Nuevo',
        notas TEXT DEFAULT '',
        fecha_alta TEXT DEFAULT (date('now')),
        ultimo_contacto TEXT DEFAULT '',
        place_id TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS historial(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        fecha TEXT DEFAULT (datetime('now')),
        tipo TEXT, detalle TEXT
    );
    CREATE TABLE IF NOT EXISTS config(
        clave TEXT PRIMARY KEY,
        valor TEXT DEFAULT ''
    );
    INSERT OR IGNORE INTO config(clave,valor) VALUES('api_key','');
    INSERT OR IGNORE INTO config(clave,valor) VALUES('oferta_texto','');
    """)
    con.commit(); con.close()

def get_cfg(k):
    con = get_db()
    r = con.execute("SELECT valor FROM config WHERE clave=?",(k,)).fetchone()
    con.close()
    return r["valor"] if r else ""

def set_cfg(k, v):
    con = get_db()
    con.execute("INSERT OR REPLACE INTO config(clave,valor) VALUES(?,?)",(k,v))
    con.commit(); con.close()

def wa_url(phone, msg):
    p = "".join(c for c in (phone or "") if c.isdigit())
    if not p: return ""
    if p.startswith("0"): p = "54" + p[1:]
    elif not p.startswith("54"): p = "54" + p
    return f"https://api.whatsapp.com/send?phone={p}&text={urllib.parse.quote(msg)}"

def pers(tpl, c):
    n = c.get("nombre","")
    a = c.get("direccion","")
    z = c.get("zona","") or extraer_zona(a)
    t = c.get("telefono","")
    return tpl.replace("{nombre}",n).replace("{direccion}",a).replace("{zona}",z).replace("{telefono}",t)

MSGS = {
    "Bazar y Hogar": "Hola {nombre}! Somos importadores directos de articulos para el hogar y bazar. Esta semana tenemos ofertas increibles al por mayor. Le interesaria ver nuestras novedades?",
    "Ferreteria": "Hola {nombre}! Somos importadores mayoristas de herramientas y ferreteria. Precios imbatibles con stock permanente. Le cuento nuestras novedades?",
    "Electronica": "Hola {nombre}! Somos importadores de electronica y accesorios. Cada semana ingresa mercaderia nueva a precios mayoristas. Le interesa recibir nuestras ofertas?"
}
MGEN = "Hola {nombre}! Somos importadores directos y queremos ofrecerle articulos al mejor precio mayorista. Podemos contarle nuestras ofertas de esta semana? Muchas gracias!"
MOF  = "Hola {nombre}! Le mandamos las OFERTAS DE LA SEMANA:\n\n{oferta}\n\nPrecios mayoristas, entrega inmediata. Le interesa hacer un pedido?"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/clientes")
def api_clientes():
    q=request.args.get("q",""); estado=request.args.get("estado","")
    rubro=request.args.get("rubro",""); orden=request.args.get("orden","nombre")
    desc=request.args.get("desc","0")=="1"
    cols_ok={"nombre","estado","rubro","zona","ultimo_contacto","telefono"}
    if orden not in cols_ok: orden="nombre"
    sql="SELECT * FROM clientes WHERE 1=1"; params=[]
    if q: sql+=" AND (nombre LIKE ? OR telefono LIKE ? OR zona LIKE ?)"; params+=[f"%{q}%"]*3
    if estado: sql+=" AND estado=?"; params.append(estado)
    if rubro: sql+=" AND rubro=?"; params.append(rubro)
    sql+=f" ORDER BY {orden} COLLATE NOCASE {'DESC' if desc else 'ASC'}"
    con=get_db(); rows=[dict(r) for r in con.execute(sql,params).fetchall()]; con.close()
    ICOS={"Nuevo":"🔵","Contactado":"🟡","Interesado":"🟢","Cliente":"✅","No interesa":"❌"}
    for r in rows: r["ico"]=ICOS.get(r["estado"],"🔵")
    return jsonify(rows)

@app.route("/api/clientes", methods=["POST"])
def crear_cliente():
    d=request.json
    if not d.get("nombre"): return jsonify({"error":"Nombre requerido"}),400
    con=get_db()
    cur=con.execute("INSERT INTO clientes(nombre,telefono,direccion,zona,rubro,estado,notas) VALUES(?,?,?,?,?,?,?)",
        (d["nombre"],d.get("telefono",""),d.get("direccion",""),d.get("zona",""),
         d.get("rubro","Otro"),d.get("estado","Nuevo"),d.get("notas","")))
    con.execute("INSERT INTO historial(cliente_id,tipo,detalle) VALUES(?,?,?)",(cur.lastrowid,"Alta","Agregado manualmente"))
    con.commit(); con.close()
    return jsonify({"ok":True})

@app.route("/api/clientes/<int:cid>", methods=["PUT"])
def editar_cliente(cid):
    d=request.json; con=get_db()
    con.execute("UPDATE clientes SET nombre=?,telefono=?,direccion=?,zona=?,rubro=?,estado=?,notas=? WHERE id=?",
        (d["nombre"],d.get("telefono",""),d.get("direccion",""),d.get("zona",""),
         d.get("rubro","Otro"),d.get("estado","Nuevo"),d.get("notas",""),cid))
    con.execute("INSERT INTO historial(cliente_id,tipo,detalle) VALUES(?,?,?)",(cid,"Edicion","Datos actualizados"))
    con.commit(); con.close()
    return jsonify({"ok":True})

@app.route("/api/clientes/<int:cid>", methods=["DELETE"])
def eliminar_cliente(cid):
    con=get_db()
    con.execute("DELETE FROM historial WHERE cliente_id=?",(cid,))
    con.execute("DELETE FROM clientes WHERE id=?",(cid,))
    con.commit(); con.close()
    return jsonify({"ok":True})

@app.route("/api/clientes/<int:cid>/contactar", methods=["POST"])
def contactar(cid):
    hoy=datetime.now().strftime("%Y-%m-%d"); con=get_db()
    con.execute("UPDATE clientes SET ultimo_contacto=? WHERE id=?",(hoy,cid))
    con.execute("INSERT INTO historial(cliente_id,tipo,detalle) VALUES(?,?,?)",(cid,"WhatsApp","Mensaje enviado"))
    con.commit(); con.close()
    return jsonify({"ok":True})

@app.route("/api/buscar")
def api_buscar():
    if not HAS_REQUESTS: return jsonify({"error":"requests no instalado"}),500
    api_key=get_cfg("api_key")
    if not api_key: return jsonify({"error":"Sin API Key configurada"}),400
    query=request.args.get("q",""); barrios=request.args.get("barrios","").split(",")
    if not query: return jsonify({"error":"Falta query"}),400
    import time; seen=set(); results=[]
    for barrio in barrios:
        barrio=barrio.strip()
        if not barrio: continue
        try:
            data=req.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query":f"{query} {barrio}","language":"es","key":api_key},timeout=10).json()
            places=data.get("results",[])
            tok=data.get("next_page_token")
            for _ in range(2):
                if tok:
                    time.sleep(2)
                    d2=req.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                        params={"pagetoken":tok,"key":api_key},timeout=10).json()
                    places.extend(d2.get("results",[])); tok=d2.get("next_page_token")
            for p in places:
                pid=p.get("place_id")
                if pid and pid not in seen:
                    seen.add(pid); addr=p.get("formatted_address","")
                    results.append({"name":p.get("name",""),"address":addr,"phone":None,
                                    "rating":p.get("rating",0),"place_id":pid,"zona":extraer_zona(addr)})
        except: pass
    for p in results:
        try:
            dr=req.get("https://maps.googleapis.com/maps/api/place/details/json",
                params={"place_id":p["place_id"],"fields":"formatted_phone_number","key":api_key},timeout=8).json()
            p["phone"]=dr.get("result",{}).get("formatted_phone_number","")
        except: pass
    return jsonify(results)

@app.route("/api/guardar_busqueda", methods=["POST"])
def guardar_busqueda():
    places=request.json.get("places",[]); rubro=request.json.get("rubro","Otro")
    con=get_db(); guardados=0
    for p in places:
        existe=con.execute("SELECT id FROM clientes WHERE nombre=? AND direccion=?",
                           (p["name"],p.get("address",""))).fetchone()
        if not existe:
            cur=con.execute("INSERT INTO clientes(nombre,telefono,direccion,zona,rubro,place_id) VALUES(?,?,?,?,?,?)",
                (p["name"],p.get("phone","") or "",p.get("address",""),p.get("zona",""),rubro,p.get("place_id","")))
            con.execute("INSERT INTO historial(cliente_id,tipo,detalle) VALUES(?,?,?)",
                (cur.lastrowid,"Alta","Importado desde busqueda"))
            guardados+=1
    con.commit(); con.close()
    return jsonify({"guardados":guardados})

@app.route("/api/oferta/links", methods=["POST"])
def oferta_links():
    oferta=request.json.get("oferta",""); estado=request.json.get("estado",""); rubro=request.json.get("rubro","")
    sql="SELECT * FROM clientes WHERE telefono!='' AND telefono IS NOT NULL"; params=[]
    if estado: sql+=" AND estado=?"; params.append(estado)
    if rubro: sql+=" AND rubro=?"; params.append(rubro)
    con=get_db(); rows=[dict(r) for r in con.execute(sql,params).fetchall()]; con.close()
    links=[]
    for c in rows:
        msg=pers(MOF.replace("{oferta}",oferta),c)
        url=wa_url(c["telefono"],msg)
        if url: links.append({"id":c["id"],"nombre":c["nombre"],"url":url,"telefono":c["telefono"]})
    return jsonify(links)

@app.route("/api/oferta/marcar_enviados", methods=["POST"])
def marcar_enviados():
    ids=request.json.get("ids",[]); hoy=datetime.now().strftime("%Y-%m-%d"); con=get_db()
    for cid in ids:
        con.execute("UPDATE clientes SET ultimo_contacto=? WHERE id=?",(hoy,cid))
        con.execute("INSERT INTO historial(cliente_id,tipo,detalle) VALUES(?,?,?)",(cid,"Oferta","Oferta semanal enviada"))
    con.commit(); con.close()
    return jsonify({"ok":True})

@app.route("/api/stats")
def api_stats():
    con=get_db()
    total=con.execute("SELECT COUNT(*) as n FROM clientes").fetchone()["n"]
    con_tel=con.execute("SELECT COUNT(*) as n FROM clientes WHERE telefono!=''").fetchone()["n"]
    por_estado=con.execute("SELECT estado,COUNT(*) as n FROM clientes GROUP BY estado").fetchall()
    por_rubro=con.execute("SELECT rubro,COUNT(*) as n FROM clientes GROUP BY rubro ORDER BY n DESC").fetchall()
    hoy=datetime.now().strftime("%Y-%m-%d")
    hoy_c=con.execute("SELECT COUNT(*) as n FROM clientes WHERE ultimo_contacto=?",(hoy,)).fetchone()["n"]
    sin=con.execute("SELECT COUNT(*) as n FROM clientes WHERE ultimo_contacto='' OR ultimo_contacto IS NULL").fetchone()["n"]
    con.close()
    return jsonify({"total":total,"con_tel":con_tel,"hoy":hoy_c,"sin_contactar":sin,
        "por_estado":[dict(r) for r in por_estado],"por_rubro":[dict(r) for r in por_rubro]})

@app.route("/api/config")
def load_config():
    return jsonify({"api_key":get_cfg("api_key"),"oferta_texto":get_cfg("oferta_texto")})

@app.route("/api/config", methods=["POST"])
def save_config():
    for k,v in request.json.items(): set_cfg(k,v)
    return jsonify({"ok":True})

if __name__=="__main__":
    init_db()
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port, debug=False)
