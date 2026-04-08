from django.shortcuts import render

# Create your views here.

from django.contrib.auth import authenticate, login
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

@api_view(['POST'])
def login_api(request):
    username = request.data.get('username')
    password = request.data.get('password')

    # Validación simple de campos
    if not username or not password:
        return Response({"error": "Usuario y contraseña requeridos"}, status=status.HTTP_400_BAD_REQUEST)

    # Autenticación
    user = authenticate(username=username, password=password)

    if user is not None:
        if user.is_active:
            login(request, user)
            request.session.cycle_key() # Seguridad: Regenera la sesión
            return Response({
                "success": True, 
                "username": user.username,
                "message": "Sesión iniciada correctamente"
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Usuario inactivo"}, status=status.HTTP_403_FORBIDDEN)
    
    return Response({"error": "Credenciales inválidas"}, status=status.HTTP_401_UNAUTHORIZED)

from .models import CarouselItem
from .serializers import CarouselItemSerializer

@api_view(['GET'])
def get_carousel_items(request):
    items = CarouselItem.objects.all().order_by('order')
    serializer = CarouselItemSerializer(items, many=True)
    return Response(serializer.data)

from django.contrib.auth import logout
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['POST'])
def logout_api(request):
    logout(request) # Esto invalida la sesión en Django/Postgres
    return Response({"success": True, "message": "Sesión cerrada"}, status=200)