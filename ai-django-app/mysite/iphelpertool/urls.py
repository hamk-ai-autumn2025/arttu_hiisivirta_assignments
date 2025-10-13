from django.urls import path
from . import views

app_name = "iphelpertool"

urlpatterns = [
    path('', views.home, name='home'),
    path('save-subnet/', views.save_subnet, name='save_subnet'),
]
