from typing import Optional

from pydantic import BaseModel, Field

from .auth import AuthConfig


class SignInOptions(BaseModel):
    google: bool = Field(default=False, description="Enable Google sign-in")
    github: bool = Field(default=False, description="Enable GitHub sign-in")
    facebook: bool = Field(default=False, description="Enable Facebook sign-in")
    twitter: bool = Field(default=False, description="Enable Twitter sign-in")
    emailAndPassword: bool = Field(
        default=False, description="Enable email and password sign-in"
    )
    magicLink: bool = Field(default=False, description="Enable magic link sign-in")


class FirebaseConfig(BaseModel):
    apiKey: str
    authDomain: str
    projectId: str
    storageBucket: str
    messagingSenderId: str
    appId: str

    class Config:
        json_schema_extra = {
            "description": "Firebase config as as describe in https://firebase.google.com/docs/web/learn-more#config-object"
        }


class FirebaseExtensionConfig(BaseModel):
    signInOptions: SignInOptions
    siteName: str = Field(description="The name of the site")
    signInSuccessUrl: str = Field(
        default="/", description="The URL to redirect to after a successful sign-in"
    )
    tosLink: Optional[str] = Field(None, description="Link to the terms of service")
    privacyPolicyLink: Optional[str] = Field(
        None, description="Link to the privacy policy"
    )
    firebaseConfig: FirebaseConfig


def get_firebase_audience(c: FirebaseExtensionConfig) -> str:
    return c.firebaseConfig.projectId


def get_firebase_issuer(c: FirebaseExtensionConfig) -> str:
    return f"https://securetoken.google.com/{c.firebaseConfig.projectId}"


def get_firebase_auth_config(c: FirebaseExtensionConfig) -> AuthConfig:
    return AuthConfig(
        issuer=get_firebase_issuer(c),
        jwks_url="https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com",
        audience=get_firebase_audience(c),
    )
