IA Vidrios - Autopartes Centro v6 FIJA

Cambios pedidos:
- La clave API de OpenAI queda fija: la app la lee automáticamente desde .streamlit/secrets.toml.
- Las listas de precios quedan fijas: la app carga automáticamente todos los Excel dentro de la carpeta listas_precios.
- No hace falta subir listas en cada búsqueda.
- El nombre del archivo se usa como nombre del proveedor.

CÓMO DEJAR FIJA LA API KEY
1) Entrá a la carpeta .streamlit
2) Copiá el archivo secrets.toml.example
3) Pegalo en la misma carpeta y renombralo a secrets.toml
4) Abrilo y reemplazá:
   OPENAI_API_KEY="sk-tu-clave-api-aqui"
   por tu clave real.
5) Guardá.

IMPORTANTE:
- No compartas el archivo secrets.toml.
- Si usás Streamlit Cloud, cargá el mismo texto en Settings > Secrets.

CÓMO DEJAR FIJAS LAS LISTAS DE PRECIOS
1) Entrá a la carpeta listas_precios
2) Copiá ahí todos los Excel de proveedores que quieras comparar.
3) Renombrá cada Excel con el nombre del proveedor. Ejemplos:
   Pilkington.xlsx
   Proveedor_Cordoba.xlsx
   XYG.xlsx
4) Reiniciá la app.

CÓMO EJECUTAR
En la carpeta de la app, abrí CMD y ejecutá:
python -m streamlit run app.py

PARA USAR DESDE CELULAR EN EL MISMO WIFI
python -m streamlit run app.py --server.address 0.0.0.0
Después abrí en el celular:
http://IP-DE-TU-PC:8501

FUNCIONES
- Detecta marca, modelo y año/generación desde foto.
- Busca parabrisas, vidrio puerta/lateral, luneta o todos.
- Compara todas las listas fijas de proveedores.
- Muestra el proveedor con mejor precio.
- Mantiene candado de marca + modelo + año/generación para evitar resultados incorrectos.
