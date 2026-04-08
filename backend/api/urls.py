from django.urls import path
from .views import login_api, get_carousel_items, logout_api

urlpatterns = [
    path('login/', login_api, name='login_api'),
    path('carrusel/', get_carousel_items, name='get_carousel_items'),
    path('logout/', logout_api, name='logout_api'),
]