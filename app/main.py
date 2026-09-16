from fastapi import FastAPI

app = FastAPI(title="Nana Lanches")


@app.get("/health")
def health():
    return {"status": "ok"}
