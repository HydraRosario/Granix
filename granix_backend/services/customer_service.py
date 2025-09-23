import logging
from uuid import uuid4
import firebase_admin
from firebase_admin import firestore

from shared_utils import geocode_address

# Configurar logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class CustomerService:
    def __init__(self):
        try:
            firebase_admin.get_app()
        except ValueError:
            raise ConnectionError("Firebase Admin no está inicializado.")
        self.db = firestore.client()
        self.collection_ref = self.db.collection('customers')

    def find_customer_by_address(self, address: str):
        """Busca un cliente por su dirección en Firestore y devuelve sus datos y su ID."""
        try:
            docs = self.collection_ref.where('address', '==', address).limit(1).stream()
            for doc in docs:
                customer_data = doc.to_dict()
                customer_data['id'] = doc.id
                return customer_data
        except Exception as e:
            logger.error(f"Error al buscar cliente por dirección '{address}' en Firestore: {e}")
        return None

    def upsert_customer(self, data: dict, source_type: str):
        """
        Crea o actualiza un cliente en Firestore, evitando escrituras innecesarias.
        """
        address = data.get('delivery_address') or data.get('address')
        if not address or address == 'No encontrado':
            return None

        existing_customer = self.find_customer_by_address(address)

        if existing_customer:
            logger.info(f"Cliente encontrado en Firestore ({existing_customer['id']}). Verificando actualizaciones desde '{source_type}'.")
            update_data = {}

            if source_type == 'delivery_report':
                new_commercial_name = data.get('commercial_entity')
                if new_commercial_name and new_commercial_name != existing_customer.get('commercial_name'):
                    update_data['commercial_name'] = new_commercial_name

                new_instructions = data.get('delivery_instructions')
                if new_instructions and new_instructions != 'No encontrado' and new_instructions != existing_customer.get('delivery_instructions'):
                    update_data['delivery_instructions'] = new_instructions
            
            elif source_type == 'invoice':
                new_client_name = data.get('client_name')
                if new_client_name and new_client_name != existing_customer.get('client_name'):
                    update_data['client_name'] = new_client_name

            if update_data:
                update_data['last_updated_at'] = firestore.SERVER_TIMESTAMP
                self.collection_ref.document(existing_customer['id']).update(update_data)
                logger.info(f"Cambios detectados. Actualizando cliente: {update_data}")
                # Devolver el estado actualizado del cliente
                updated_customer_data = self.collection_ref.document(existing_customer['id']).get().to_dict()
                updated_customer_data['id'] = existing_customer['id']
                return updated_customer_data
            else:
                logger.info("No se detectaron cambios. Se omite la escritura en la base de datos.")
                return existing_customer

        else:
            # --- Cliente Nuevo: Crear registro --- 
            logger.info(f"Cliente nuevo. Creando entrada en Firestore desde '{source_type}'.")
            new_customer_id = uuid4().hex
            coordinates = geocode_address(address)
            
            new_customer = {
                'id': new_customer_id,
                'address': address,
                'coordinates': coordinates,
                'client_name': data.get('client_name') if source_type == 'invoice' else None,
                'commercial_name': data.get('commercial_entity') if source_type == 'delivery_report' else None,
                'delivery_instructions': data.get('delivery_instructions') if source_type == 'delivery_report' else None,
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_updated_at': firestore.SERVER_TIMESTAMP
            }
            
            self.collection_ref.document(new_customer_id).set(new_customer)
            return new_customer