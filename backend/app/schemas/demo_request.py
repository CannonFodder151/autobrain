from pydantic import BaseModel, EmailStr, Field


class DemoRequest(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=100)
    company: str = Field(default="", max_length=100)
    honeypot: str = Field(default="", max_length=0)


class DemoResponse(BaseModel):
    status: str
    message: str
    login_url: str = "https://demo.autobrainservice.app"
