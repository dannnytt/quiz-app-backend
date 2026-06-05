from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings

security = HTTPBearer(auto_error=False)

async def get_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Проверяет токен администратора"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    
    if credentials.credentials != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    return credentials.credentials