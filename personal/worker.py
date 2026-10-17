"""One platform worker: isolated connections and a fair round across active accounts."""
import signal
import time
from .app import create_app
from .accounts import connect
from .connections import settings
from .messaging import process_one, stamp


def run_round(accounts, recovered, transport=None):
    errors = 0
    for account in accounts.all(active_only=True):
        try:
            with connect(accounts.database(account)) as connection:
                if account['id'] not in recovered:
                    connection.execute("UPDATE message_jobs SET state='uncertain',detail='Proceso interrumpido. Revisa el resultado antes de reenviar.',updated_at=? WHERE state='sending'", (stamp(),))
                    connection.commit()
                    recovered.add(account['id'])
                options = {'config':settings(connection)}
                if transport is not None:
                    options['transport'] = transport
                process_one(connection, **options)
        except Exception:
            errors += 1
    return errors


def main():
    app = create_app()
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    recovered = set()
    while running:
        try:
            if run_round(app.extensions['accounts'], recovered):
                print('No se pudieron procesar algunos espacios; el resto continúa.', flush=True)
        except Exception:
            print('El trabajador encontró un error; revisa los estados de la cola.', flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
