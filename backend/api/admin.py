from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import CarouselItem

@admin.register(CarouselItem)
class CarouselItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'order') # Para ver el título y el orden en la lista
    ordering = ('order',)             # Para que en el admin salgan ordenados