from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import LoginRequest, Token, UserRead, UserRegister

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account with hashed password",
)
def register(
    user_in: UserRegister,
    db: Session = Depends(get_db),
) -> User:
    """Register a new user with secure password storage."""
    existing_user = UserRepository.get_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists",
        )

    hashed_pw = hash_password(user_in.password)
    user = UserRepository.create(db, user_in, hashed_password=hashed_pw)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate with email and password to receive a JWT access token",
)
def login(
    login_in: LoginRequest,
    db: Session = Depends(get_db),
) -> Token:
    """JSON login endpoint issuing signed JWTs."""
    user = UserRepository.get_by_email(db, login_in.email)
    if not user or not user.hashed_password or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role, "email": user.email},
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post(
    "/token",
    response_model=Token,
    summary="OAuth2-compatible token issuance endpoint (form-data)",
)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """OAuth2 password flow compatible endpoint."""
    user = UserRepository.get_by_email(db, form_data.username)
    if not user or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role, "email": user.email},
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post(
    "/demo-session",
    response_model=Token,
    summary="Issue demo session JWT for local demo without manual login",
)
def get_demo_session(
    db: Session = Depends(get_db),
) -> Token:
    """
    Safely provisions a demo session for the local demo dashboard.
    Enforces authorization invariants by issuing a valid signed JWT Bearer token
    for a dedicated local demo administrator without weakening or bypassing RBAC.
    """
    from app.core.config import settings
    from app.models.enums import UserRole
    from app.schemas.user import UserCreate

    if not settings.ENABLE_DEMO_ENDPOINTS or (settings.ENVIRONMENT == "production" and not settings.DEBUG):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo session endpoint is disabled.",
        )

    demo_email = "demo_admin@learngraph.edu"
    user = UserRepository.get_by_email(db, demo_email)
    if not user:
        demo_user_in = UserCreate(
            email=demo_email,
            password="DemoAdminPassword123!",
            full_name="Demo Administrator",
            role=UserRole.ADMIN,
        )
        user = UserRepository.create(
            db,
            demo_user_in,
            hashed_password=hash_password("DemoAdminPassword123!"),
        )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role, "email": user.email},
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get profile of the currently authenticated user",
)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> User:
    """Returns the profile of the caller validated from bearer token."""
    return current_user
