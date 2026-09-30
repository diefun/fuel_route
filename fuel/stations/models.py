from django.db import models

# Create your models here.
class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    price = models.DecimalField(decimal_places=5, max_digits=10)
    latitude = models.DecimalField(decimal_places=6, max_digits=9, null=True, blank=True)
    longitude = models.DecimalField(decimal_places=6, max_digits=9, null=True, blank=True)
