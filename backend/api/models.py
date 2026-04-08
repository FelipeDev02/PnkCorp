from django.db import models

class CarouselItem(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    # Cambiamos URLField por ImageField y definimos la subcarpeta
    image = models.ImageField(upload_to='carousel_img/') 
    order = models.IntegerField(default=0)

    def __str__(self):
        return self.title