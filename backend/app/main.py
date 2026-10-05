from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, dashboard, health, products, sales
from app.core.config import settings

app = FastAPI(
    title="Sabi-Stock API",
    description="API foundation for the Sabi-Stock inventory management application.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(sales.router, prefix="/api/sales", tags=["sales"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
