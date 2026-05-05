import os, re, json, base64, urllib.parse
from io import BytesIO

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz
from openai import OpenAI

st.set_page_config(page_title="IA Vidrios - Autopartes Centro", page_icon="🚗", layout="centered")
st.title("🚗 Buscador IA de vidrios")
st.caption("Sacá o subí una foto, elegí el tipo de vidrio y compará precios entre proveedores ya cargados.")

LISTAS_DIR = "listas_precios"

# API Key fija: se lee automáticamente desde .streamlit/secrets.toml o desde variable de entorno.
def get_api_key():
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        key = ""
    return key or os.getenv("OPENAI_API_KEY", "")

api_key = get_api_key()
if api_key:
    st.sidebar.success("🔑 API Key cargada automáticamente")
else:
    st.sidebar.error("Falta API Key fija")
    st.sidebar.caption('Crea el archivo .streamlit/secrets.toml con tu clave de OpenAI')

pieza = st.selectbox(
    "¿Qué querés buscar?",
    ["Parabrisas", "Vidrio de puerta / lateral", "Luneta", "Todos los vidrios"],
)

st.subheader("📋 Listas de precios fijas")
st.caption("La app carga automáticamente todos los Excel que estén dentro de la carpeta 'listas_precios'. El nombre del archivo se usa como nombre del proveedor.")

modo_foto = st.radio("Foto del auto", ["Subir foto", "Sacar foto con cámara"], horizontal=True)
if modo_foto == "Sacar foto con cámara":
    image_file = st.camera_input("Sacá una foto del auto")
else:
    image_file = st.file_uploader("Subí una foto del auto", type=["jpg", "jpeg", "png", "webp"])

@st.cache_data
def load_excel_from_bytes(data: bytes):
    # Admite listas simples donde las primeras 3 columnas sean código/descripcion/precio.
    # Si tiene encabezados, intenta encontrarlos. Si no, usa las primeras 3 columnas.
    raw = pd.read_excel(BytesIO(data), header=None)
    raw = raw.dropna(how="all")
    if raw.empty:
        return pd.DataFrame(columns=["codigo", "descripcion", "precio"])

    # Detectar fila de encabezado posible.
    header_row = None
    for idx in range(min(10, len(raw))):
        vals = [normalize_for_header(x) for x in raw.iloc[idx].tolist()]
        has_desc = any(v in ["descripcion", "detalle", "producto", "articulo", "nombre"] for v in vals)
        has_price = any(v in ["precio", "importe", "valor", "lista"] for v in vals)
        if has_desc and has_price:
            header_row = idx
            break

    if header_row is not None:
        dfh = pd.read_excel(BytesIO(data), header=header_row)
        cols = list(dfh.columns)
        code_col = find_col(cols, ["codigo", "cod", "code", "sku"])
        desc_col = find_col(cols, ["descripcion", "detalle", "producto", "articulo", "nombre"])
        price_col = find_col(cols, ["precio", "importe", "valor", "lista"])
        if desc_col is not None and price_col is not None:
            out = pd.DataFrame({
                "codigo": dfh[code_col] if code_col is not None else "",
                "descripcion": dfh[desc_col],
                "precio": dfh[price_col],
            })
        else:
            out = raw.iloc[:, :3].copy()
            out.columns = ["codigo", "descripcion", "precio"]
    else:
        out = raw.iloc[:, :3].copy()
        out.columns = ["codigo", "descripcion", "precio"]

    out = out.dropna(subset=["descripcion"])
    out["codigo"] = out["codigo"].astype(str).str.strip()
    out["descripcion"] = out["descripcion"].astype(str).str.strip()
    out["precio"] = parse_price_series(out["precio"])
    out = out.dropna(subset=["precio"], how="all")
    return out

def normalize_for_header(x):
    t = str(x).strip().lower()
    repl = {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ñ":"n"}
    for a,b in repl.items():
        t = t.replace(a,b)
    t = re.sub(r"[^a-z0-9]+", "", t)
    return t

def find_col(cols, names):
    norm = [normalize_for_header(c) for c in cols]
    for n in names:
        nn = normalize_for_header(n)
        for i, c in enumerate(norm):
            if nn == c or nn in c:
                return cols[i]
    return None

def parse_price_series(s):
    def parse_one(x):
        if pd.isna(x):
            return pd.NA
        if isinstance(x, (int, float)):
            return float(x)
        t = str(x).strip()
        t = re.sub(r"[^0-9,\.\-]", "", t)
        if not t:
            return pd.NA
        # Formatos AR: 1.234.567,89 o 123456,78
        if "," in t and "." in t:
            if t.rfind(",") > t.rfind("."):
                t = t.replace(".", "").replace(",", ".")
            else:
                t = t.replace(",", "")
        elif "," in t:
            t = t.replace(".", "").replace(",", ".")
        else:
            # Si tiene muchos puntos, son separadores de miles.
            if t.count(".") > 1:
                t = t.replace(".", "")
        try:
            return float(t)
        except Exception:
            return pd.NA
    return s.map(parse_one)

@st.cache_data
def load_excel_from_path(path: str):
    with open(path, "rb") as f:
        return load_excel_from_bytes(f.read())

def proveedor_from_filename(filename: str) -> str:
    base = os.path.splitext(os.path.basename(filename))[0]
    return base.replace("_", " ").replace("-", " ").strip() or base

def load_price_lists():
    listas = []
    os.makedirs(LISTAS_DIR, exist_ok=True)
    archivos = sorted([
        os.path.join(LISTAS_DIR, f)
        for f in os.listdir(LISTAS_DIR)
        if f.lower().endswith((".xlsx", ".xls")) and not f.startswith("~$")
    ])
    for path in archivos:
        try:
            dfp = load_excel_from_path(path)
            listas.append({"proveedor": proveedor_from_filename(path), "archivo": os.path.basename(path), "df": dfp})
        except Exception as e:
            st.warning(f"No pude cargar {os.path.basename(path)}: {e}")
    return listas

def normalize(text: str) -> str:
    text = str(text).upper()
    repl = {"Á":"A","É":"E","Í":"I","Ó":"O","Ú":"U","Ñ":"N"}
    for a, b in repl.items():
        text = text.replace(a, b)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def year_to_full(y: int) -> int:
    if y < 100:
        return 2000 + y if y <= 35 else 1900 + y
    return y

def extract_years(text: str):
    t = normalize(text)
    ranges = []
    for a, b in re.findall(r"\b(\d{2,4})\s*(?:A|AL|/|-)\s*(\d{2,4})\b", t):
        aa, bb = year_to_full(int(a)), year_to_full(int(b))
        if 1980 <= aa <= 2035 and 1980 <= bb <= 2035:
            ranges.append((min(aa, bb), max(aa, bb)))
    singles = []
    for a in re.findall(r"\b(19\d{2}|20\d{2})\b", t):
        aa = int(a)
        if 1980 <= aa <= 2035:
            singles.append(aa)
    return ranges, singles

def generation_score(desc: str, target_year: int | None, marca: str = "", modelo: str = "") -> int:
    if not target_year:
        return 0
    desc_norm = normalize(desc)
    ranges, singles = extract_years(desc_norm)
    score = 0
    for a, b in ranges:
        if a <= target_year <= b:
            score += 25
        elif target_year > b:
            score -= min(45, 12 + (target_year - b) * 2)
        elif target_year < a:
            score -= min(25, 5 + (a - target_year))
    for y in singles:
        if target_year >= y:
            score += 12
        else:
            score -= min(20, (y - target_year) * 2)
    modelo_norm = normalize(modelo)
    if "ECOSPORT" in modelo_norm and target_year >= 2013:
        if "KINETIC" in desc_norm or "2012" in desc_norm:
            score += 35
        if any(x in desc_norm for x in ["03 12", "2003 2012", "2010"]):
            score -= 55
    return score

def detect_car_with_ai(img_bytes: bytes, api_key: str, pieza: str) -> dict:
    client = OpenAI(api_key=api_key)
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    prompt = f"""
    Identifica el vehículo de la foto para buscar un vidrio automotor en una lista argentina.
    La pieza que quiere el usuario es: {pieza}.
    IMPORTANTE: distingue generación/años. No mezcles una generación vieja con una nueva.
    Si detectás Ford EcoSport 2018-2022, agregá como términos de búsqueda: ECOSPORT 2012, ECOSPORT KINETIC, ECOSPORT 2012 KINETIC.
    Devuelve SOLO JSON válido con estas claves:
    marca, modelo, anio_estimado, generacion_o_anios, confianza, pieza_buscada, terminos_busqueda, excluir_terminos.
    anio_estimado debe ser un número aproximado si podés, por ejemplo 2018.
    terminos_busqueda debe ser una lista corta con palabras para buscar en Excel.
    excluir_terminos debe incluir rangos/generaciones incorrectas si aplica, por ejemplo ["03-12", "2003-2012"] para una EcoSport 2018.
    No inventes precio. Solo identifica el auto.
    """
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"},
            ],
        }],
    )
    text = resp.output_text.strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    return json.loads(text)

def category_keywords(pieza: str):
    if pieza == "Parabrisas":
        return ["PSAS", "PARABRISAS", "PARABRISA"]
    if pieza == "Luneta":
        return ["LUNETA", "LUN"]
    if pieza == "Vidrio de puerta / lateral":
        return ["LATERAL", "LAT", "PUERTA", "PTA", "ALETA", "CUSTODIA", "VIDRIO"]
    return []

def filter_by_piece(df: pd.DataFrame, pieza: str):
    kws = category_keywords(pieza)
    if not kws:
        return df.copy()
    norm_desc = df["descripcion"].map(normalize)
    mask = norm_desc.apply(lambda d: any(k in d.split() or k in d for k in kws))
    return df[mask].copy()



def brand_required_tokens(marca=""):
    text = normalize(marca)
    aliases = {
        "FORD": ["FORD", "FO"],
        "FIAT": ["FIAT", "FI"],
        "CHEVROLET": ["CHEVROLET", "CHEV", "GM", "CH"],
        "VOLKSWAGEN": ["VOLKSWAGEN", "VW", "V W"],
        "RENAULT": ["RENAULT", "REN"],
        "PEUGEOT": ["PEUGEOT", "PEU"],
        "CITROEN": ["CITROEN", "CIT"],
        "TOYOTA": ["TOYOTA", "TOY"],
        "HONDA": ["HONDA"],
        "NISSAN": ["NISSAN"],
        "HYUNDAI": ["HYUNDAI"],
        "KIA": ["KIA"],
        "MERCEDES": ["MERCEDES", "MB", "M BENZ"],
        "BMW": ["BMW"],
        "AUDI": ["AUDI"],
    }
    for key, vals in aliases.items():
        if key in text:
            return vals
    return [tok for tok in text.split() if len(tok) >= 3 and not tok.isdigit()]

def contains_token(desc_norm: str, tokens):
    if not tokens:
        return True
    padded = f" {desc_norm} "
    for tok in tokens:
        nt = normalize(tok)
        # Para abreviaturas de marca como FO, FI, CH, exigir palabra/código separado.
        if len(nt) <= 3:
            if re.search(rf"(^|\s|-){{1}}{re.escape(nt)}($|\s|-)", desc_norm):
                return True
            if f" {nt} " in padded:
                return True
        elif nt in desc_norm:
            return True
    return False

def year_strict_match(desc: str, target_year: int | None):
    """Candado de año/generación.
    - Si la descripción trae rango 17-23, el año debe caer dentro.
    - Si trae un año único 2012, se acepta como 'desde 2012' hasta 15 años después.
    - Si no trae año, se permite pero con menor score porque algunas listas no cargan años.
    """
    if not target_year:
        return True, 0
    ranges, singles = extract_years(desc)
    if ranges:
        return any(a <= target_year <= b for a, b in ranges), 0
    if singles:
        ok = any(y <= target_year <= y + 15 for y in singles)
        return ok, (8 if ok else 0)
    return True, -10

def model_required_tokens(marca="", modelo=""):
    """Devuelve tokens que tienen que aparecer sí o sí para evitar falsos positivos.
    Ej: si detecta EcoSport, no puede devolver Corsa o Fiat Uno.
    """
    text = normalize(f"{marca} {modelo}")
    tokens = []
    # Alias frecuentes en listas argentinas
    aliases = {
        "ECOSPORT": ["ECOSPORT", "ECO SPORT"],
        "DUNA": ["DUNA"],
        "UNO": ["UNO"],
        "TORO": ["TORO"],
        "GOL": ["GOL"],
        "GOL TREND": ["GOL TREND", "TREND"],
        "FIESTA": ["FIESTA"],
        "FOCUS": ["FOCUS"],
        "CORSA": ["CORSA"],
        "ONIX": ["ONIX"],
        "KA": [" KA ", "FORD KA"],
        "RANGER": ["RANGER"],
        "S10": ["S10", "S 10"],
        "AMAROK": ["AMAROK"],
        "HILUX": ["HILUX"],
        "KANGOO": ["KANGOO"],
        "PARTNER": ["PARTNER"],
        "BERLINGO": ["BERLINGO"],
        "PALIO": ["PALIO"],
        "SIENA": ["SIENA"],
        "CRONOS": ["CRONOS"],
        "ARGO": ["ARGO"],
    }
    for key, vals in aliases.items():
        if key in text:
            tokens.extend(vals)
    # Si no detectó alias, usar palabras del modelo que no sean marca/año y tengan largo razonable.
    if not tokens:
        bad = {"FORD","FIAT","CHEVROLET","VW","VOLKSWAGEN","RENAULT","PEUGEOT","CITROEN","TOYOTA","HONDA","NISSAN","HYUNDAI","KIA","MERCEDES","BENZ","AUDI","BMW"}
        for tok in text.split():
            if tok not in bad and len(tok) >= 4 and not tok.isdigit():
                tokens.append(tok)
    return list(dict.fromkeys(tokens))

def contains_required_model(desc_norm: str, required_tokens):
    if not required_tokens:
        return True
    padded = f" {desc_norm} "
    for tok in required_tokens:
        nt = normalize(tok)
        # tokens con espacios al principio/final son buscados como palabra exacta
        if tok.startswith(" ") or tok.endswith(" "):
            if nt in padded:
                return True
        elif nt in desc_norm:
            return True
    return False

def search_prices(df: pd.DataFrame, terms, pieza: str, target_year=None, marca="", modelo="", exclude_terms=None, min_score=82):
    df_piece = filter_by_piece(df, pieza)
    if df_piece.empty:
        df_piece = df.copy()
    norm_desc = df_piece["descripcion"].map(normalize)
    clean_terms = [normalize(t) for t in terms if str(t).strip()]
    excludes = [normalize(t) for t in (exclude_terms or []) if str(t).strip()]

    # CANDADOS OBLIGATORIOS: marca + modelo + año/generación.
    brand_tokens = brand_required_tokens(marca)
    model_tokens = model_required_tokens(marca, modelo)

    rows = []
    for idx, desc_norm in norm_desc.items():
        if not clean_terms:
            continue

        # 1) Marca obligatoria: FORD/FO, FIAT/FI, CHEVROLET/CH, etc.
        if marca and not contains_token(desc_norm, brand_tokens):
            continue

        # 2) Modelo obligatorio: si detecta ECOSPORT, la descripción debe decir ECOSPORT.
        if not contains_required_model(desc_norm, model_tokens):
            continue

        # 3) Año/generación obligatorio cuando el artículo trae rango/año.
        year_ok, year_bonus = year_strict_match(desc_norm, target_year)
        if not year_ok:
            continue

        base = max(fuzz.token_set_ratio(t, desc_norm) for t in clean_terms)
        if any(t and t in desc_norm for t in clean_terms):
            base = min(100, base + 7)
        if model_tokens and contains_required_model(desc_norm, model_tokens):
            base = min(100, base + 12)
        if marca and contains_token(desc_norm, brand_tokens):
            base = min(100, base + 8)

        gen = generation_score(desc_norm, target_year, marca, modelo) + year_bonus
        penalty = 0
        if any(e and e in desc_norm for e in excludes):
            penalty -= 45
        final = max(0, min(100, int(base + gen + penalty)))
        if final >= min_score:
            r = df_piece.loc[idx].to_dict()
            r["coincidencia"] = final
            r["base_texto"] = int(base)
            r["ajuste_anio"] = int(gen + penalty)
            rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["coincidencia", "base_texto", "precio"], ascending=[False, False, True]).head(15)

def search_all_lists(listas, terms, pieza, target_year=None, marca="", modelo="", exclude_terms=None):
    todos = []
    resumen = []
    for item in listas:
        proveedor = item["proveedor"] or item["archivo"]
        results = search_prices(item["df"], terms, pieza, target_year, marca, modelo, exclude_terms)
        if not results.empty:
            results = results.copy()
            results.insert(0, "proveedor", proveedor)
            results.insert(1, "archivo", item["archivo"])
            todos.append(results)
            best = results.iloc[0].to_dict()
            resumen.append(best)
    all_df = pd.concat(todos, ignore_index=True) if todos else pd.DataFrame()
    resumen_df = pd.DataFrame(resumen)
    if not resumen_df.empty:
        resumen_df = resumen_df.sort_values(["precio", "coincidencia"], ascending=[True, False])
    if not all_df.empty:
        all_df = all_df.sort_values(["precio", "coincidencia"], ascending=[True, False])
    return resumen_df, all_df

def format_price(x):
    return f"$ {x:,.0f}".replace(",", ".") if pd.notna(x) else ""

def show_results(resumen_df, all_df, pieza, auto_txt):
    st.subheader("🏆 Mejor precio por proveedor")
    if resumen_df.empty:
        st.warning("No encontré coincidencias claras en ninguna lista.")
        return
    show = resumen_df.copy()
    show["precio"] = show["precio"].map(format_price)
    cols = ["proveedor", "codigo", "descripcion", "precio", "coincidencia", "ajuste_anio"]
    st.dataframe(show[cols], width="stretch", hide_index=True)

    best = resumen_df.iloc[0]
    st.success(f"Mejor precio: {best['proveedor']} — {best['codigo']} — {best['descripcion']} — {format_price(best['precio'])}")

    with st.expander("Ver todas las coincidencias de todas las listas"):
        all_show = all_df.copy()
        all_show["precio"] = all_show["precio"].map(format_price)
        st.dataframe(all_show[["proveedor", "codigo", "descripcion", "precio", "coincidencia", "ajuste_anio"]], width="stretch", hide_index=True)

    mensaje = f"Hola! Mejor precio encontrado: {pieza} para {auto_txt}. Proveedor: {best['proveedor']}. Código {best['codigo']} - {best['descripcion']} - {format_price(best['precio'])}."
    link = "https://wa.me/?text=" + urllib.parse.quote(mensaje)
    st.markdown(f"[📲 Enviar mejor precio por WhatsApp]({link})")

listas = load_price_lists()
if listas:
    total_productos = sum(len(x["df"]) for x in listas)
    st.info(f"Listas fijas cargadas: {len(listas)} proveedor(es) / {total_productos} productos en total")
    with st.expander("Ver proveedores cargados"):
        for x in listas:
            st.write(f"• **{x['proveedor']}** — {x['archivo']} — {len(x['df'])} productos")
else:
    st.error("No hay ninguna lista fija cargada. Copiá tus Excel dentro de la carpeta listas_precios y reiniciá la app.")

col1, col2 = st.columns(2)
with col1:
    buscar = st.button("🔎 Detectar auto y comparar precios", type="primary", disabled=not image_file or not listas)
with col2:
    if st.button("🔄 Nueva búsqueda"):
        st.rerun()

if buscar:
    if not api_key:
        st.error("Falta la OpenAI API Key para que la IA pueda leer la foto.")
        st.stop()
    img_bytes = image_file.getvalue()
    st.image(img_bytes, caption="Foto cargada", width="stretch")

    with st.spinner("Detectando auto con IA..."):
        car = detect_car_with_ai(img_bytes, api_key, pieza)

    st.subheader("Auto detectado")
    marca = car.get("marca", "")
    modelo = car.get("modelo", "")
    auto_txt = f"{marca} {modelo}".strip()
    target_year = car.get("anio_estimado")
    try:
        target_year = int(target_year) if target_year else None
    except Exception:
        target_year = None

    st.write(f"**{auto_txt}** — {car.get('generacion_o_anios','')}")
    st.write(f"Año estimado: **{target_year or 'sin dato'}**")
    st.write(f"Pieza: **{pieza}**")
    st.write(f"Confianza: **{car.get('confianza','')}**")

    terms = car.get("terminos_busqueda", []) + [auto_txt, modelo]
    exclude_terms = car.get("excluir_terminos", [])
    with st.spinner("Buscando en todas las listas y comparando precios..."):
        resumen_df, all_df = search_all_lists(listas, terms, pieza, target_year, marca, modelo, exclude_terms)
    show_results(resumen_df, all_df, pieza, auto_txt)

st.divider()
st.subheader("🔍 Búsqueda manual")
st.caption("Usala si querés buscar sin foto, corregir el modelo o comparar un artículo directo.")
col_a, col_b = st.columns(2)
with col_a:
    manual = st.text_input("Marca/modelo o palabra clave", placeholder="Ej: FORD ECOSPORT")
with col_b:
    manual_year = st.number_input("Año aprox. (opcional)", min_value=1980, max_value=2035, value=None, step=1)
if manual and listas:
    resumen_df, all_df = search_all_lists(listas, [manual], pieza, manual_year, "", manual, [])
    show_results(resumen_df, all_df, pieza, manual)

st.caption("Tip: para comparar proveedores, subí todos los Excel y poné nombres como: Pilkington, XYG, proveedor Córdoba, proveedor Buenos Aires, etc.")
