from django.urls import path

from .views import contact, customer_terms, organiser_terms, service_worker


urlpatterns = [
    path("service-worker.js", service_worker, name="service-worker"),
    path("contact/", contact, name="contact"),
    path("terms/customers/", customer_terms, name="customer-terms"),
    path("terms/organisers/", organiser_terms, name="organiser-terms"),
]
