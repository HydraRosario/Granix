# Sistema de Gestión de Transporte Granix

Este sistema de gestión de transporte (TMS) automatiza la digitalización y optimización de las operaciones de reparto. La aplicación extrae datos de informes de reparto y facturas, centraliza la información de clientes, optimiza las rutas de entrega y genera listas de carga para los transportistas.

## Arquitectura y Flujo de Datos

El sistema se compone de una API RESTful construida con Flask y una base de datos NoSQL (Firestore) para la persistencia de datos. El flujo de trabajo principal es el siguiente:

1.  **Carga de Documentos**: Los usuarios suben informes de reparto y facturas (en formato PDF o imagen) a través de endpoints específicos.
2.  **Extracción de Datos (OCR)**: Se utiliza Tesseract OCR para extraer el texto crudo de los documentos. Los PDF se convierten a imágenes previamente.
3.  **Análisis y Estructuración (Parsing)**: Módulos especializados (`delivery_parser.py`, `invoice_service.py`) analizan el texto crudo mediante expresiones regulares para extraer información estructurada como:
    *   **Informes de Reparto**: Nombre comercial, dirección de entrega, número de bultos, instrucciones especiales.
    *   **Facturas**: Razón social del cliente, dirección, detalle de productos (código, cantidad) y monto total.
4.  **Gestión de Clientes**: Un `CustomerService` centralizado gestiona la base de datos de clientes. Busca clientes por dirección para evitar duplicados y los crea o actualiza con la información más reciente. Durante la creación, las direcciones se geocodifican usando Nominatim para obtener coordenadas (latitud, longitud).
5.  **Vinculación de Datos**: El sistema vincula automáticamente las facturas procesadas con los ítems de reparto correspondientes. Esta vinculación se basa en la coincidencia de la dirección y una ventana de tiempo, enriqueciendo los datos del reparto con detalles de los productos.
6.  **Optimización de Ruta**:
    *   Las direcciones de entrega válidas se utilizan para resolver el Problema del Viajante de Comercio (TSP) usando Google OR-Tools.
    *   El algoritmo calcula la ruta más corta que visita todas las paradas, comenzando y terminando en un depósito predefinido.
    *   La ruta optimizada se enriquece con una polilínea a nivel de calle obtenida del servidor de OSRM, proporcionando una visualización detallada del trayecto.
7.  **Generación de Lista de Carga**: A partir de la ruta optimizada, se genera una **lista de carga LIFO (Last-In, First-Out)**. Esto indica al personal del depósito el orden inverso de las entregas para cargar el vehículo de manera eficiente.
8.  **Persistencia**: Todos los datos relevantes (clientes, facturas, ítems de reparto, rutas diarias) se guardan en colecciones de Firestore.

## Funcionalidades Principales

### Endpoints de la API

*   `POST /process_delivery_report`:
    *   Recibe un informe de reparto (PDF o imagen).
    *   Extrae, parsea y procesa cada línea de entrega.
    *   Crea o actualiza los clientes correspondientes.
    *   Guarda cada parada como un `delivery_item` en Firestore con estado `pending_link`.
    *   Ejecuta la optimización de ruta con las paradas válidas.
    *   Guarda la ruta optimizada y la lista de carga LIFO en la colección `daily_routes`.
    *   Devuelve un JSON con los datos procesados, la ruta y la lista de carga.

*   `POST /process_invoice`:
    *   Recibe una o varias facturas (PDF de una o varias páginas, o imágenes).
    *   Para cada factura, extrae los datos, sube una copia a Cloudinary y guarda la información en Firestore.
    *   Intenta vincular la factura con un `delivery_item` existente que coincida en dirección y tenga estado `pending_link`.
    *   Si la vinculación es exitosa, el estado del `delivery_item` cambia a `linked` y se enriquece con los detalles de los productos de la factura.

*   `GET /geocode?address=<direccion>`:
    *   Endpoint de utilidad para geocodificar una dirección. Devuelve las coordenadas.

## Estructura del Proyecto

*   `app.py`: Punto de entrada de la aplicación Flask.
*   `routes.py`: Define los endpoints de la API y orquesta el flujo de datos entre los servicios.
*   `shared_utils.py`: Módulo de utilidades transversales:
    *   Inicialización de Firebase y Cloudinary.
    *   Función de geocodificación (`geocode_address`) con lógica de normalización y fallback.
    *   Funciones para extracción de texto (OCR) y manipulación de archivos.
*   `delivery_parser.py`: Contiene la clase `DeliveryReportParser`, responsable de analizar el texto de los informes de reparto y extraer los datos de cada entrega.
*   `delivery_service.py`: Orquesta el procesamiento de un informe de reparto completo, incluyendo la interacción con `CustomerService` y `route_optimizer`.
*   `invoice_service.py`: Orquesta el procesamiento de facturas, incluyendo el parseo, la subida a Cloudinary y la lógica de vinculación con `delivery_items`.
*   `customer_service.py`: Encapsula la lógica de negocio para la gestión de clientes en Firestore (CRUD y búsqueda).
*   `route_optimizer.py`: Contiene la lógica para la optimización de rutas (TSP con OR-Tools) y la obtención de la ruta a nivel de calle (OSRM).

## Estructura de la Base de Datos (Firestore)

*   **`customers`**:
    *   **ID**: UUID.
    *   **Campos**: `address`, `coordinates`, `client_name` (razón social), `commercial_name` (nombre de fantasía), `delivery_instructions`.
*   **`invoices`**:
    *   **ID**: UUID.
    *   **Campos**: `invoiceNumber`, `cloudinaryImageUrl`, `parsedData` (con `product_items`), `location`, `status`.
*   **`delivery_items`**:
    *   **ID**: UUID.
    *   **Campos**: `delivery_address`, `commercial_entity`, `packages`, `customer_id`, `status` (`pending_link`, `linked`, `review_required`), `invoice_id` (tras la vinculación), `product_items` (denormalizado desde la factura).
*   **`daily_routes`**:
    *   **ID**: Fecha del día (`YYYY-MM-DD`).
    *   **Campos**: `optimized_route` (lista de paradas ordenadas), `optimized_loading_list` (LIFO), `street_level_polyline`, `created_at`.

## Librerías Clave

*   **Flask**: Framework web para la API.
*   **firebase-admin**: SDK de Firebase para Python.
*   **google-cloud-firestore**: Cliente de Firestore.
*   **pdf2image** y **Pillow**: Procesamiento de PDFs e imágenes.
*   **pytesseract**: Wrapper de Tesseract OCR para Python.
*   **geopy**: Geocodificación de direcciones.
*   **ortools**: Optimización de rutas (TSP).
*   **polyline** y **requests**: Para decodificar y obtener rutas de OSRM.
*   **cloudinary**: Almacenamiento de imágenes en la nube.

---

## Información de Desarrollo

Esta sección contiene notas importantes para el desarrollo y mantenimiento de la aplicación.

### Gestión de la Base de Datos

*   **Base de Datos Vacía**: La aplicación está diseñada para funcionar correctamente con una base de datos Firestore vacía. Las consultas que no encuentran documentos (por ejemplo, al buscar un cliente existente) no generan errores. En su lugar, la lógica de negocio interpreta que el registro es nuevo y procede a crearlo.

*   **Índices de Firestore**: Ciertas consultas en la aplicación, especialmente aquellas que filtran por un campo y ordenan por otro, requieren un **índice compuesto** en Firestore para funcionar.
    *   **Error Común**: Si una consulta requiere un índice que no existe, la API de Firestore devolverá un error `400 Bad Request` con un mensaje claro: `The query requires an index`.
    *   **Solución**: El mensaje de error incluirá una URL única que lleva directamente a la consola de Firebase para crear el índice faltante con la configuración exacta. Simplemente sigue el enlace y haz clic en "Crear Índice". Este proceso es mandatorio y no puede ser evitado mediante código.

### Lógica de Vinculación (Reparto-Factura)

La lógica actual para vincular una factura individual con una parada de un informe de reparto (`delivery_item`) ha sido modificada para soportar clientes recurrentes. Ahora, al subir una factura, el sistema buscará el `delivery_item` más antiguo con estado `pending_link` que coincida con la dirección, sin importar la fecha.

**Mejora Futura Sugerida**: La lógica actual es simple y podría ser insuficiente si múltiples repartos para la misma dirección quedan pendientes. Una mejora futura podría ser presentar una interfaz en el frontend que permita al usuario seleccionar manualmente a qué `delivery_item` pendiente desea vincular la factura cuando se detectan múltiples candidatos.
