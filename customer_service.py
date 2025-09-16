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
        Crea o actualiza un cliente en Firestore basado en la fuente de datos.
        - `address` es la clave principal.
        - `delivery_report` actualiza `commercial_name` e `delivery_instructions`.
        - `invoice` actualiza `client_name`.
        """
        address = data.get('delivery_address') or data.get('address')
        if not address or address == 'No encontrado':
            return None

        existing_customer = self.find_customer_by_address(address)

        if existing_customer:
            # --- Cliente Existente: Actualizar campos específicos --- 
            logger.info(f"Cliente encontrado en Firestore ({existing_customer['id']}). Actualizando desde '{source_type}'.")
            update_data = {
                'last_updated_at': firestore.SERVER_TIMESTAMP
            }
            
            if source_type == 'delivery_report':
                if data.get('commercial_entity'):
                    update_data['commercial_name'] = data['commercial_entity']
                if data.get('delivery_instructions') and data['delivery_instructions'] != 'No encontrado':
                    update_data['delivery_instructions'] = data['delivery_instructions']
            
            elif source_type == 'invoice':
                if data.get('client_name'):
                    update_data['client_name'] = data['client_name']

            if len(update_data) > 1: # Si hay algo más que el timestamp para actualizar
                self.collection_ref.document(existing_customer['id']).update(update_data)
                logger.info(f"Datos actualizados para el cliente: {update_data}")

            # Devolver el estado completo del cliente
            updated_customer_data = self.collection_ref.document(existing_customer['id']).get().to_dict()
            updated_customer_data['id'] = existing_customer['id']
            return updated_customer_data

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
