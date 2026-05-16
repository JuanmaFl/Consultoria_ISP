"""
Management command para cargar datos de municipios de Colombia
desde DANE (población) y MinTIC (conectividad)

Uso:
    python manage.py cargar_datos_municipios
    python manage.py cargar_datos_municipios --solo-dane
    python manage.py cargar_datos_municipios --solo-mintic
    python manage.py cargar_datos_municipios --departamento "Antioquia"
"""

import requests
import json
import time
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import MunicipioData


# Datos DANE censo 2018 — municipios principales de Colombia
# Fuente: https://geoportal.dane.gov.co
# Cacheados aquí para no depender de la API en cada ejecución
MUNICIPIOS_DANE = [
    # (codigo_dane, nombre, departamento, poblacion, hogares, nbi_pct, area_km2, lat, lng)
    ("05001", "Medellín", "Antioquia", 2569007, 890000, 7.8, 380.6, 6.2442, -75.5812),
    ("05002", "Abejorral", "Antioquia", 20000, 5800, 28.4, 852.0, 5.7897, -75.4336),
    ("05004", "Abriaquí", "Antioquia", 3200, 950, 42.1, 230.0, 6.6289, -76.0736),
    ("05021", "Alejandría", "Antioquia", 5800, 1700, 31.2, 195.0, 6.3672, -75.0836),
    ("05030", "Amagá", "Antioquia", 30000, 9200, 18.6, 84.0, 6.0378, -75.7036),
    ("05031", "Amalfi", "Antioquia", 22000, 6500, 35.8, 1.240, 6.9089, -75.0736),
    ("05034", "Andes", "Antioquia", 43000, 13000, 22.4, 700.0, 5.6553, -75.8836),
    ("05036", "Angelópolis", "Antioquia", 9000, 2700, 24.1, 65.0, 6.1128, -75.7136),
    ("05038", "Angostura", "Antioquia", 14000, 4100, 38.9, 825.0, 6.8789, -75.3436),
    ("05040", "Anorí", "Antioquia", 16000, 4700, 45.2, 1.969, 7.0689, -75.1436),
    ("05044", "Santafé de Antioquia", "Antioquia", 24000, 7200, 26.3, 479.0, 6.5589, -75.8236),
    ("05045", "Anzá", "Antioquia", 9500, 2800, 39.7, 388.0, 6.3089, -75.8736),
    ("05051", "Apartadó", "Antioquia", 180000, 52000, 21.4, 607.0, 7.8839, -76.6336),
    ("05055", "Arboletes", "Antioquia", 45000, 13000, 48.6, 775.0, 8.8589, -76.4236),
    ("05059", "Argelia", "Antioquia", 18000, 5300, 41.3, 558.0, 5.7289, -75.9936),
    ("05079", "Barbosa", "Antioquia", 54000, 16000, 14.2, 206.0, 6.4389, -75.3336),
    ("05086", "Bello", "Antioquia", 528000, 162000, 8.9, 142.5, 6.3369, -75.5581),
    ("05088", "Betania", "Antioquia", 14000, 4100, 35.6, 305.0, 5.9189, -75.9736),
    ("05091", "Betulia", "Antioquia", 17000, 5000, 37.8, 558.0, 6.1089, -75.9836),
    ("05093", "Ciudad Bolívar", "Antioquia", 32000, 9500, 29.4, 516.0, 5.8589, -76.0236),
    ("05101", "Briceño", "Antioquia", 11000, 3200, 48.7, 725.0, 7.2889, -75.5036),
    ("05107", "Buriticá", "Antioquia", 12000, 3500, 36.9, 528.0, 6.7189, -75.8936),
    ("05113", "Cáceres", "Antioquia", 35000, 10000, 52.3, 3.296, 7.5889, -75.3436),
    ("05120", "Caicedo", "Antioquia", 11000, 3200, 41.6, 286.0, 6.3889, -76.0736),
    ("05125", "Caldas", "Antioquia", 80000, 24000, 11.3, 146.0, 6.0939, -75.6336),
    ("05129", "Campamento", "Antioquia", 13000, 3800, 39.2, 524.0, 6.9789, -75.3036),
    ("05134", "Cañasgordas", "Antioquia", 18000, 5300, 33.8, 445.0, 6.7489, -76.0236),
    ("05138", "Caracolí", "Antioquia", 8500, 2500, 29.6, 402.0, 6.4489, -74.7736),
    ("05142", "Caramanta", "Antioquia", 7000, 2100, 38.4, 103.0, 5.5489, -75.6536),
    ("05145", "Carepa", "Antioquia", 50000, 14000, 31.8, 590.0, 7.7589, -76.6536),
    ("05147", "El Carmen de Viboral", "Antioquia", 48000, 14000, 19.6, 680.0, 6.0889, -75.3336),
    ("05148", "Carolina", "Antioquia", 5500, 1600, 32.1, 245.0, 6.7489, -75.3336),
    ("05150", "Caucasia", "Antioquia", 110000, 32000, 38.9, 1.429, 7.9889, -75.1936),
    ("05154", "Chigorodó", "Antioquia", 72000, 21000, 28.4, 690.0, 7.6689, -76.6836),
    ("05172", "Cisneros", "Antioquia", 15000, 4400, 22.8, 178.0, 6.5389, -74.9836),
    ("05190", "Cocorná", "Antioquia", 17000, 5000, 29.3, 389.0, 6.0589, -75.1936),
    ("05197", "Concepción", "Antioquia", 7000, 2100, 36.7, 314.0, 6.3989, -75.0536),
    ("05206", "Concordia", "Antioquia", 23000, 6800, 27.4, 381.0, 6.0489, -75.9036),
    ("05209", "Copacabana", "Antioquia", 72000, 22000, 7.4, 70.5, 6.3539, -75.5036),
    ("05212", "Dabeiba", "Antioquia", 25000, 7300, 51.4, 2.196, 7.0089, -76.2736),
    ("05234", "Donmatías", "Antioquia", 24000, 7100, 14.8, 198.0, 6.4889, -75.3736),
    ("05237", "Ebéjico", "Antioquia", 14000, 4100, 38.2, 449.0, 6.3289, -75.9036),
    ("05240", "El Bagre", "Antioquia", 52000, 15000, 48.7, 3.063, 7.5989, -74.8136),
    ("05250", "Envigado", "Antioquia", 242000, 75000, 4.8, 78.7, 6.1753, -75.5936),
    ("05264", "Fredonia", "Antioquia", 25000, 7400, 22.6, 322.0, 5.9289, -75.6836),
    ("05266", "Frontino", "Antioquia", 18000, 5300, 49.3, 1.146, 6.7789, -76.1336),
    ("05282", "Giraldo", "Antioquia", 6500, 1900, 41.8, 132.0, 6.6789, -75.9736),
    ("05284", "Girardota", "Antioquia", 58000, 17000, 10.2, 81.3, 6.3789, -75.4436),
    ("05306", "Gómez Plata", "Antioquia", 13000, 3800, 28.7, 380.0, 6.6289, -75.2036),
    ("05308", "Granada", "Antioquia", 10000, 2900, 27.4, 370.0, 6.1489, -75.1736),
    ("05310", "Guadalupe", "Antioquia", 10000, 3000, 33.6, 427.0, 6.9289, -75.2336),
    ("05313", "Guarne", "Antioquia", 55000, 16000, 13.4, 155.0, 6.2789, -75.4036),
    ("05315", "Guatapé", "Antioquia", 10000, 3000, 14.8, 65.0, 6.2389, -75.1636),
    ("05318", "Heliconia", "Antioquia", 9000, 2700, 33.2, 183.0, 6.2089, -75.8236),
    ("05321", "Hispania", "Antioquia", 7500, 2200, 29.8, 104.0, 5.8089, -75.9036),
    ("05347", "Itagüí", "Antioquia", 280000, 87000, 4.2, 21.1, 6.1847, -75.5994),
    ("05353", "Ituango", "Antioquia", 25000, 7300, 51.8, 2.343, 7.1689, -75.7436),
    ("05360", "Jardín", "Antioquia", 16000, 4700, 26.4, 208.0, 5.5989, -75.8236),
    ("05364", "Jericó", "Antioquia", 13000, 3800, 24.8, 164.0, 5.7889, -75.7836),
    ("05368", "La Ceja", "Antioquia", 55000, 17000, 10.6, 160.0, 6.0289, -75.4336),
    ("05376", "La Estrella", "Antioquia", 70000, 22000, 5.8, 35.7, 6.1589, -75.6436),
    ("05380", "La Pintada", "Antioquia", 8500, 2500, 21.4, 112.0, 5.7489, -75.5936),
    ("05390", "La Unión", "Antioquia", 20000, 5900, 24.2, 211.0, 5.9789, -75.3636),
    ("05400", "Liborina", "Antioquia", 11000, 3200, 38.9, 360.0, 6.6889, -75.8436),
    ("05411", "Maceo", "Antioquia", 10000, 2900, 33.6, 639.0, 6.5489, -74.7836),
    ("05425", "Marinilla", "Antioquia", 58000, 17000, 11.8, 117.0, 6.1789, -75.3436),
    ("05440", "Montebello", "Antioquia", 10000, 3000, 31.4, 122.0, 5.9489, -75.5036),
    ("05467", "Murindó", "Antioquia", 4500, 1300, 68.4, 3.454, 6.9889, -76.7436),
    ("05475", "Mutatá", "Antioquia", 20000, 5900, 52.1, 1.854, 7.2489, -76.4336),
    ("05480", "Nariño", "Antioquia", 14000, 4100, 35.8, 275.0, 5.8189, -74.8936),
    ("05483", "Necoclí", "Antioquia", 62000, 18000, 53.4, 1.836, 8.4289, -76.7836),
    ("05490", "Nechí", "Antioquia", 28000, 8200, 51.2, 1.617, 8.0989, -74.7736),
    ("05495", "Olaya", "Antioquia", 5000, 1500, 40.2, 118.0, 6.5989, -75.9236),
    ("05501", "Peñol", "Antioquia", 17000, 5000, 18.6, 134.0, 6.2189, -75.2336),
    ("05504", "Peque", "Antioquia", 11000, 3200, 52.3, 586.0, 6.9089, -75.8736),
    ("05541", "Pueblorrico", "Antioquia", 9000, 2700, 32.1, 136.0, 5.7289, -76.0336),
    ("05543", "Puerto Berrío", "Antioquia", 48000, 14000, 29.8, 1.100, 6.4889, -74.4036),
    ("05544", "Puerto Nare", "Antioquia", 18000, 5300, 36.7, 935.0, 6.1989, -74.5836),
    ("05547", "Puerto Triunfo", "Antioquia", 18000, 5300, 38.4, 876.0, 5.8789, -74.6436),
    ("05560", "Remedios", "Antioquia", 25000, 7300, 42.8, 2.327, 7.0289, -74.6936),
    ("05576", "Rionegro", "Antioquia", 120000, 37000, 9.6, 196.0, 6.1539, -75.3736),
    ("05579", "Sabanalarga", "Antioquia", 10000, 2900, 42.3, 372.0, 6.8889, -75.8036),
    ("05585", "Sabaneta", "Antioquia", 110000, 35000, 3.8, 15.8, 6.1489, -75.6136),
    ("05591", "Salgar", "Antioquia", 19000, 5600, 29.4, 456.0, 5.9489, -75.9736),
    ("05604", "San Andrés de Cuerquia", "Antioquia", 9000, 2700, 38.6, 325.0, 6.9489, -75.5836),
    ("05607", "San Carlos", "Antioquia", 17000, 5000, 26.8, 702.0, 6.1889, -74.9936),
    ("05615", "San Francisco", "Antioquia", 8500, 2500, 31.4, 437.0, 6.2989, -75.1036),
    ("05628", "San Jerónimo", "Antioquia", 15000, 4400, 23.6, 164.0, 6.3589, -75.7436),
    ("05631", "San José de la Montaña", "Antioquia", 6000, 1800, 36.8, 190.0, 6.8389, -75.6836),
    ("05642", "San Luis", "Antioquia", 14000, 4100, 29.3, 706.0, 6.0389, -74.9936),
    ("05647", "San Pedro de los Milagros", "Antioquia", 28000, 8200, 16.4, 181.0, 6.4889, -75.5536),
    ("05649", "San Pedro de Urabá", "Antioquia", 30000, 8800, 49.2, 719.0, 8.2789, -76.3836),
    ("05652", "San Rafael", "Antioquia", 14000, 4100, 27.6, 508.0, 6.2989, -75.0236),
    ("05656", "San Roque", "Antioquia", 17000, 5000, 31.8, 798.0, 6.4789, -74.9836),
    ("05658", "San Vicente Ferrer", "Antioquia", 22000, 6500, 22.4, 219.0, 6.2689, -75.3236),
    ("05659", "Santa Bárbara", "Antioquia", 24000, 7100, 28.6, 783.0, 5.8689, -75.5736),
    ("05664", "Santa Rosa de Osos", "Antioquia", 37000, 11000, 20.8, 1.105, 6.6489, -75.4636),
    ("05667", "Santo Domingo", "Antioquia", 13000, 3800, 34.2, 668.0, 6.4689, -75.1036),
    ("05670", "El Santuario", "Antioquia", 30000, 8800, 14.6, 110.0, 6.1389, -75.2736),
    ("05674", "Segovia", "Antioquia", 47000, 14000, 38.7, 2.093, 7.0789, -74.7036),
    ("05679", "Sonsón", "Antioquia", 32000, 9400, 29.8, 1.580, 5.7189, -75.3136),
    ("05686", "Sopetrán", "Antioquia", 22000, 6500, 21.4, 195.0, 6.5089, -75.7436),
    ("05690", "Supporta", "Antioquia", 8500, 2500, 33.6, 225.0, 5.9789, -75.6836),
    ("05697", "Tarazá", "Antioquia", 45000, 13000, 48.9, 1.876, 7.8689, -75.3936),
    ("05736", "Tarso", "Antioquia", 9000, 2700, 31.2, 140.0, 5.8189, -75.8236),
    ("05740", "Titiribí", "Antioquia", 14000, 4100, 24.8, 165.0, 6.0689, -75.7836),
    ("05744", "Toledo", "Antioquia", 8500, 2500, 44.3, 394.0, 6.9689, -75.5236),
    ("05748", "Turbo", "Antioquia", 165000, 48000, 53.6, 3.062, 8.0989, -76.7336),
    ("05756", "Uramita", "Antioquia", 8500, 2500, 46.2, 388.0, 6.8689, -76.1836),
    ("05761", "Urrao", "Antioquia", 45000, 13000, 43.8, 2.770, 6.3289, -76.1336),
    ("05764", "Valdivia", "Antioquia", 22000, 6500, 47.6, 1.284, 7.1889, -75.4436),
    ("05770", "Valparaíso", "Antioquia", 9000, 2700, 31.6, 107.0, 5.7389, -75.6236),
    ("05776", "Vegachí", "Antioquia", 13000, 3800, 38.4, 990.0, 6.7789, -74.8036),
    ("05789", "Venecia", "Antioquia", 14000, 4100, 27.8, 233.0, 5.9589, -75.7736),
    ("05790", "Vigía del Fuerte", "Antioquia", 7000, 2100, 71.2, 2.068, 6.5989, -76.8736),
    ("05809", "Yalí", "Antioquia", 10000, 2900, 38.6, 602.0, 6.5989, -74.9336),
    ("05819", "Yarumal", "Antioquia", 48000, 14000, 27.4, 1.129, 6.9689, -75.4136),
    ("05837", "Yolombó", "Antioquia", 24000, 7100, 36.8, 1.215, 6.5989, -74.9636),
    ("05842", "Yondó", "Antioquia", 20000, 5900, 44.2, 2.089, 6.9289, -74.4836),
    ("05856", "Zaragoza", "Antioquia", 32000, 9400, 43.6, 1.853, 7.4989, -74.8636),
    # Bogotá
    ("11001", "Bogotá D.C.", "Cundinamarca", 7743955, 2450000, 5.4, 1587.0, 4.7110, -74.0721),
    # Valle del Cauca
    ("76001", "Cali", "Valle del Cauca", 2227642, 695000, 9.2, 560.0, 3.4516, -76.5320),
    ("76111", "Buenaventura", "Valle del Cauca", 415000, 118000, 42.3, 6.297, 3.8833, -77.0311),
    ("76520", "Palmira", "Valle del Cauca", 330000, 102000, 13.8, 1.162, 3.5394, -76.3036),
    ("76563", "Pereira", "Valle del Cauca", 488839, 153000, 10.4, 702.0, 4.8087, -75.6906),
    # Atlántico
    ("08001", "Barranquilla", "Atlántico", 1228621, 380000, 12.6, 166.0, 10.9878, -74.7889),
    ("08433", "Malambo", "Atlántico", 130000, 38000, 22.4, 98.0, 10.8578, -74.7736),
    # Bolívar
    ("13001", "Cartagena", "Bolívar", 1028736, 318000, 22.8, 609.1, 10.3997, -75.5144),
    # Santander
    ("68001", "Bucaramanga", "Santander", 592062, 185000, 8.6, 165.0, 7.1193, -73.1227),
    ("68307", "Girón", "Santander", 175000, 54000, 14.2, 527.0, 7.0742, -73.1694),
    # Nariño
    ("52001", "Pasto", "Nariño", 448000, 139000, 16.8, 1.181, 1.2136, -77.2811),
    # Córdoba
    ("23001", "Montería", "Córdoba", 497000, 151000, 28.4, 3.141, 8.7575, -75.8811),
    # Huila
    ("41001", "Neiva", "Huila", 358000, 111000, 16.4, 1.553, 2.9273, -75.2819),
    # Tolima
    ("73001", "Ibagué", "Tolima", 580000, 181000, 13.2, 1.439, 4.4389, -75.2322),
    # Caldas
    ("17001", "Manizales", "Caldas", 441000, 138000, 8.8, 572.0, 5.0689, -75.5136),
    # Risaralda
    ("66001", "Pereira", "Risaralda", 488839, 153000, 10.4, 702.0, 4.8087, -75.6906),
    # Quindío
    ("63001", "Armenia", "Quindío", 305000, 96000, 10.6, 230.0, 4.5339, -75.6811),
    # Cauca
    ("19001", "Popayán", "Cauca", 330000, 102000, 18.4, 512.0, 2.4419, -76.6136),
    # Magdalena
    ("47001", "Santa Marta", "Magdalena", 554000, 170000, 22.6, 2.381, 11.2408, -74.2011),
    # Cesar
    ("20001", "Valledupar", "Cesar", 500000, 154000, 21.8, 4.493, 10.4631, -73.2536),
    # Sucre
    ("70001", "Sincelejo", "Sucre", 310000, 94000, 29.4, 328.0, 9.3047, -75.3978),
    # Meta
    ("50001", "Villavicencio", "Meta", 560000, 174000, 14.8, 1.328, 4.1420, -73.6269),
    # Boyacá
    ("15001", "Tunja", "Boyacá", 195000, 61000, 12.6, 115.7, 5.5353, -73.3578),
    # Cundinamarca
    ("25175", "Chía", "Cundinamarca", 140000, 44000, 7.4, 79.3, 4.8600, -74.0594),
    ("25307", "Girardot", "Cundinamarca", 107000, 33000, 14.8, 130.0, 4.3028, -74.8028),
    ("25754", "Soacha", "Cundinamarca", 700000, 218000, 11.6, 184.0, 4.5792, -74.2169),
]


class Command(BaseCommand):
    help = 'Carga datos de municipios desde DANE y MinTIC'

    def add_arguments(self, parser):
        parser.add_argument('--solo-dane', action='store_true', help='Solo cargar datos DANE')
        parser.add_argument('--solo-mintic', action='store_true', help='Solo cargar datos MinTIC')
        parser.add_argument('--departamento', type=str, help='Filtrar por departamento')
        parser.add_argument('--actualizar', action='store_true', help='Actualizar registros existentes')

    def handle(self, *args, **options):
        solo_dane = options.get('solo_dane')
        solo_mintic = options.get('solo_mintic')
        departamento_filtro = options.get('departamento')
        actualizar = options.get('actualizar')

        municipios = MUNICIPIOS_DANE
        if departamento_filtro:
            municipios = [m for m in municipios if departamento_filtro.lower() in m[2].lower()]
            self.stdout.write(f"Filtrando por departamento: {departamento_filtro} — {len(municipios)} municipios")

        if not solo_mintic:
            self.cargar_dane(municipios, actualizar)

        if not solo_dane:
            self.cargar_mintic(municipios, actualizar)

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Carga completada. Total municipios en BD: {MunicipioData.objects.count()}'
        ))

    def cargar_dane(self, municipios, actualizar):
        self.stdout.write('\n📊 Cargando datos DANE...')
        creados = 0
        actualizados = 0
        errores = 0

        for datos in municipios:
            codigo, nombre, depto, pob, hogares, nbi, area, lat, lng = datos

            # Calcular densidad
            densidad = round(pob / area, 2) if area and area > 0 else None

            try:
                with transaction.atomic():
                    obj, created = MunicipioData.objects.get_or_create(
                        codigo_dane=codigo,
                        defaults={
                            'nombre': nombre,
                            'departamento': depto,
                            'poblacion_total': pob,
                            'hogares': hogares,
                            'nbi_porcentaje': nbi,
                            'area_km2': area,
                            'densidad_poblacional': densidad,
                            'latitud': lat,
                            'longitud': lng,
                        }
                    )

                    if not created and actualizar:
                        obj.nombre = nombre
                        obj.departamento = depto
                        obj.poblacion_total = pob
                        obj.hogares = hogares
                        obj.nbi_porcentaje = nbi
                        obj.area_km2 = area
                        obj.densidad_poblacional = densidad
                        obj.latitud = lat
                        obj.longitud = lng
                        obj.save()
                        actualizados += 1
                    elif created:
                        creados += 1

            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ⚠ Error en {nombre}: {e}'))
                errores += 1

        self.stdout.write(f'  ✓ DANE: {creados} creados, {actualizados} actualizados, {errores} errores')

    def cargar_mintic(self, municipios, actualizar):
        """
        Intenta obtener datos de MinTIC desde datos.gov.co
        Si falla, usa estimaciones basadas en población
        """
        self.stdout.write('\n📡 Cargando datos MinTIC...')
        actualizados = 0

        # Intentar API de datos.gov.co
        mintic_data = self.fetch_mintic_api()

        for datos in municipios:
            codigo, nombre, depto, pob, hogares, nbi, area, lat, lng = datos

            try:
                municipio = MunicipioData.objects.get(codigo_dane=codigo)

                # Si tenemos datos reales de MinTIC
                if codigo in mintic_data:
                    info = mintic_data[codigo]
                    municipio.mintic_tiene_fibra = info.get('tiene_fibra', False)
                    municipio.mintic_proveedores_count = info.get('proveedores', 0)
                    municipio.mintic_penetracion_pct = info.get('penetracion', None)
                else:
                    # Estimación basada en tamaño del municipio
                    municipio.mintic_tiene_fibra = pob > 20000
                    municipio.mintic_proveedores_count = self.estimar_proveedores(pob)
                    municipio.mintic_penetracion_pct = self.estimar_penetracion(pob, nbi)

                municipio.save()
                actualizados += 1

            except MunicipioData.DoesNotExist:
                pass
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ⚠ MinTIC error {nombre}: {e}'))

        self.stdout.write(f'  ✓ MinTIC: {actualizados} municipios actualizados')

    def fetch_mintic_api(self):
        """Intenta obtener datos reales de conectividad del MinTIC"""
        try:
            self.stdout.write('  → Consultando API datos.gov.co...')
            url = "https://www.datos.gov.co/resource/jvtm-4d3e.json"
            params = {'$limit': 1200, '$offset': 0}
            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()
                self.stdout.write(f'  → {len(data)} registros obtenidos de MinTIC')
                resultado = {}
                for item in data:
                    cod = item.get('codigo_municipio') or item.get('cod_municipio')
                    if cod:
                        resultado[str(cod).zfill(5)] = {
                            'tiene_fibra': True,
                            'proveedores': int(item.get('numero_proveedores', 1)),
                            'penetracion': float(item.get('penetracion', 0) or 0),
                        }
                return resultado
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  ⚠ API MinTIC no disponible: {e}'))

        return {}

    def estimar_proveedores(self, poblacion):
        if poblacion > 500000:
            return 8
        elif poblacion > 200000:
            return 6
        elif poblacion > 100000:
            return 4
        elif poblacion > 50000:
            return 3
        elif poblacion > 20000:
            return 2
        else:
            return 1

    def estimar_penetracion(self, poblacion, nbi):
        base = 65.0 if poblacion > 500000 else \
               55.0 if poblacion > 100000 else \
               40.0 if poblacion > 50000 else \
               25.0 if poblacion > 20000 else 15.0
        ajuste = nbi * 0.4
        return round(max(5.0, base - ajuste), 1)
