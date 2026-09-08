"""
Procesa los BulkQueryJob que quedaron en estado 'pending'.
Disenado para correr por cron cada minuto.
"""
import time
import traceback

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import BulkQueryJob
from api.utils_csv import CSVProcessor
from api.views_bulk_query import procesar_consultas_sincronico

CHUNK = 50


class Command(BaseCommand):
    help = "Procesa jobs de consulta masiva en estado pending"

    def add_arguments(self, parser):
        parser.add_argument('--job-id', type=int, default=None,
                            help='Procesar solo este job')
        parser.add_argument('--max-jobs', type=int, default=5,
                            help='Maximo de jobs por corrida')

    def handle(self, *args, **options):
        procesados = 0
        limite = options['max_jobs']

        while procesados < limite:
            job = self._tomar_job(options['job_id'])
            if job is None:
                break
            self._procesar(job)
            procesados += 1

        if procesados == 0:
            self.stdout.write("Sin jobs pendientes.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Jobs procesados: {procesados}"))

    def _tomar_job(self, job_id):
        """Toma un job pending y lo marca processing de forma atomica."""
        with transaction.atomic():
            qs = BulkQueryJob.objects.select_for_update(
                skip_locked=True
            ).filter(status='pending').order_by('fecha_creacion')
            if job_id:
                qs = qs.filter(id=job_id)
            job = qs.first()
            if job is None:
                return None
            job.status = 'processing'
            job.fecha_inicio = timezone.now()
            job.registros_procesados = 0
            job.save(update_fields=['status', 'fecha_inicio', 'registros_procesados'])
            return job

    def _procesar(self, job):
        inicio = time.time()
        self.stdout.write(f"Job {job.id}: iniciando ({job.total_registros} registros)")
        try:
            job.archivo_entrada.open('rb')
            try:
                formato, registros = CSVProcessor.parse_csv(job.archivo_entrada)
            finally:
                job.archivo_entrada.close()

            validos = [r for r in registros if r.get('tipo') != 'error']
            if not validos:
                raise ValueError("El archivo no contiene registros validos")

            resultados = []
            for i in range(0, len(validos), CHUNK):
                chunk = validos[i:i + CHUNK]
                resultados.extend(procesar_consultas_sincronico(chunk, formato))
                job.registros_procesados = len(resultados)
                job.save(update_fields=['registros_procesados'])
                self.stdout.write(f"  {len(resultados)}/{len(validos)}")

            csv_output = CSVProcessor.generate_output_csv(resultados)
            filename = f'resultado_{job.id}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv'
            job.archivo_salida.save(
                filename,
                ContentFile(csv_output.encode('utf-8-sig')),
                save=False
            )

            job.status = 'completed'
            job.total_registros = len(validos)
            job.registros_procesados = len(resultados)
            job.error_mensaje = None
            job.fecha_finalizacion = timezone.now()
            job.save()

            dur = time.time() - inicio
            self.stdout.write(self.style.SUCCESS(
                f"Job {job.id}: completado en {dur:.1f}s"))

        except Exception as exc:
            job.status = 'failed'
            job.error_mensaje = f"{type(exc).__name__}: {exc}"
            job.fecha_finalizacion = timezone.now()
            job.save(update_fields=['status', 'error_mensaje', 'fecha_finalizacion'])
            self.stderr.write(self.style.ERROR(f"Job {job.id}: FALLO -> {exc}"))
            traceback.print_exc()
