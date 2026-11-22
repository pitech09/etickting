from django.urls import path

from .views import LoginView, LogoutView, OrganiserRegisterView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("register/organiser/", OrganiserRegisterView.as_view(), name="register-organiser"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
