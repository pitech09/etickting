from django.urls import path

from .views import contact, organiser_terms, customer_terms


urlpatterns = [
    path("contact/", contact, name="contact"),
    path("terms/customers/", customer_terms, name="customer-terms"),
    path("terms/organisers/", organiser_terms, name="organiser-terms"),
]
