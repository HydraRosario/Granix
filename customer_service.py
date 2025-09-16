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
            raise ConnectionError("Firebase Admin no está inicializado. Asegúrate de que se inicialice antes de usar CustomerService.")
        self.db = firestore.client()
        self.collection_ref = self.db.collection('customers')

    def find_customer_by_address(self, address: str):
        """Busca un cliente por su dirección en Firestore y devuelve sus datos y su ID."""
        try:
            docs = self.collection_ref.where('address', '==', address).limit(1).stream()
            for doc in docs:
                customer_data = doc.to_dict()
                customer_data['id'] = doc.id  # Añadir el ID del documento
                return customer_data
        except Exception as e:
            logger.error(f"Error al buscar cliente por dirección '{address}' en Firestore: {e}")
        return None

    def upsert_customer(self, customer_info: dict):
        """
        Busca un cliente por dirección en Firestore. Si existe, devuelve sus datos.
        Si no existe, lo crea, obtiene coordenadas y lo guarda en Firestore.
        """
        address = customer_info.get('delivery_address') or customer_info.get('address')
        if not address or address == 'No encontrado':
            logger.warning("No se proporcionó una dirección válida para upsert.")
            return None

        customer_name = customer_info.get('commercial_entity') or customer_info.get('client_name')

        existing_customer = self.find_customer_by_address(address)

        if existing_customer:
            logger.info(f"Cliente encontrado en Firestore para la dirección: {address}")
            new_instructions = customer_info.get('delivery_instructions')
            if new_instructions and new_instructions != 'No encontrado' and existing_customer.get('delivery_instructions') != new_instructions:
                logger.info(f"Actualizando instrucciones de entrega para el cliente {existing_customer['id']}")
                self.collection_ref.document(existing_customer['id']).update({'delivery_instructions': new_instructions})
                existing_customer['delivery_instructions'] = new_instructions # Actualizar el objeto en memoria
            return existing_customer
        else:
            logger.info(f"Cliente nuevo. Creando entrada en Firestore para la dirección: {address}")
            new_customer_id = uuid4().hex
            coordinates = geocode_address(address)
            
            new_customer = {
                'commercial_name': customer_name,
                'address': address,
                'coordinates': coordinates,
                'delivery_instructions': customer_info.get('delivery_instructions', 'No encontrado'),
                'created_at': firestore.SERVER_TIMESTAMP
            }
            
            self.collection_ref.document(new_customer_id).set(new_customer)
            new_customer['id'] = new_customer_id # Añadir id para retorno
            return new_customer