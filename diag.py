import sqlite3, os, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

print("=" * 50)
print("1. DATABASE / CREDENTIALS CHECK")
print("=" * 50)

db_path = "chats.db"
print(f"DB file exists : {os.path.exists(db_path)}")
print(f"DB size        : {os.path.getsize(db_path)} bytes")

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in c.fetchall()]
print(f"Tables         : {tables}")

c.execute("SELECT username, created_at FROM users")
users = c.fetchall()
print(f"Total users    : {len(users)}")
for u in users:
    print(f"  User: {u[0]}  (created: {u[1]})")

c.execute("SELECT COUNT(*) FROM threads")
print(f"Chat threads   : {c.fetchone()[0]}")

c.execute("SELECT COUNT(*) FROM messages")
print(f"Total messages : {c.fetchone()[0]}")

conn.close()

print()
print("=" * 50)
print("2. GEMINI EMBEDDING CHECK")
print("=" * 50)
from langchain_google_genai import GoogleGenerativeAIEmbeddings
key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
print(f"API key found  : {bool(key)}")
try:
    t0 = time.time()
    emb = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=key)
    vec = emb.embed_query("hello world test")
    print(f"Embedding OK   : dim={len(vec)}  ({time.time()-t0:.1f}s)")
except Exception as e:
    print(f"Embedding FAIL : {e}")

print()
print("=" * 50)
print("3. GEMINI LLM CHECK")
print("=" * 50)
from langchain_google_genai import ChatGoogleGenerativeAI
try:
    t0 = time.time()
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.2, google_api_key=key)
    resp = llm.invoke([("human", "Reply with exactly: OK")])
    print(f"LLM OK         : response='{resp.content.strip()}'  ({time.time()-t0:.1f}s)")
except Exception as e:
    print(f"LLM FAIL       : {e}")

print()
print("=" * 50)
print("4. FAISS VECTOR STORE CHECK")
print("=" * 50)
from langchain_community.vectorstores import FAISS
import glob, json
faiss_dirs = glob.glob("faiss_index_*")
print(f"FAISS indexes  : {faiss_dirs}")
for idx_dir in faiss_dirs:
    meta_file = f"{idx_dir}_meta.json"
    if os.path.exists(meta_file):
        with open(meta_file) as f:
            meta = json.load(f)
        print(f"  {idx_dir}:")
        print(f"     Files   : {meta.get('files', [])}")
        print(f"     Pages   : {meta.get('pages', 0)}")
        print(f"     Chunks  : {meta.get('chunks', 0)}")
        print(f"     Provider: {meta.get('embed_provider', 'unknown')}")
        try:
            emb2 = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=key)
            vs = FAISS.load_local(idx_dir, emb2, allow_dangerous_deserialization=True)
            results = vs.similarity_search("test", k=1)
            print(f"     Search  : OK ({len(results)} result(s))")
        except Exception as e:
            print(f"     Search  : FAIL - {e}")

print()
print("=" * 50)
print("5. OCR DEPENDENCIES CHECK")
print("=" * 50)
try:
    import fitz
    print(f"pymupdf        : OK (v{fitz.version[0]})")
except ImportError as e:
    print(f"pymupdf        : MISSING - {e}")
try:
    from google import genai as gai
    print(f"google-genai   : OK")
except ImportError as e:
    print(f"google-genai   : MISSING - {e}")

print()
print("=" * 50)
print("ALL CHECKS COMPLETE")
print("=" * 50)
