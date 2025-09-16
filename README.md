# Sistema de Gestión de Transporte Granix

Este documento describe las funcionalidades y la arquitectura técnica del sistema de gestión de transporte Granix. El objetivo principal de la aplicación es automatizar la extracción de datos de documentos de transporte (informes de reparto y facturas) para centralizar y gestionar la información de los clientes y sus entregas.

---

## Funcionalidades Principales

El sistema opera a través de una API REST que ofrece dos funcionalidades clave:

### 1. Carga de Informes de Reparto

Esta funcionalidad permite al usuario subir un archivo (PDF o imagen) de un informe de reparto.

**Flujo de Proceso:**

1.  **Recepción del Archivo:** El endpoint (`/process_delivery_report`) recibe el archivo.
2.  **Extracción de Texto (OCR):**
    *   Si el archivo es un PDF, primero se convierte cada página en una imagen.
    *   Se utiliza tecnología de Reconocimiento Óptico de Caracteres (OCR) para extraer todo el texto crudo del documento.
3.  **Análisis y Estructuración de Datos:**
    *   El texto crudo pasa a un parser especializado (`delivery_parser.py`) que, mediante expresiones regulares, localiza y extrae la información relevante de cada línea de entrega.
    *   Los datos extraídos para cada entrega incluyen: **Nombre Comercial**, **Dirección de Entrega**, **Número de Bultos** e **Instrucciones de Entrega**.
4.  **Integración con la Base de Datos de Clientes:**
    *   Cada cliente extraído del informe se procesa a través del `CustomerService`.
    *   El sistema busca en la base de datos de Firestore un cliente existente con la misma **dirección**.
    *   **Si el cliente no existe**, se crea un nuevo registro. Se obtiene su geolocalización (coordenadas) y se guarda junto con el nombre comercial y las instrucciones de entrega.
    *   **Si el cliente ya existe**, el sistema actualiza su registro con la información más reciente del informe (nombre comercial e instrucciones de entrega), enriqueciendo el perfil del cliente sin duplicar datos.

### 2. Carga de Facturas

Permite al usuario subir uno o varios archivos de facturas, ya sea como imágenes individuales o en un único PDF de múltiples páginas.

**Flujo de Proceso:**

1.  **Recepción y Procesamiento de Archivos:** El endpoint (`/process_invoice`) recibe el/los archivo(s). De manera similar al informe de reparto, los PDFs se convierten en imágenes.
2.  **Extracción de Texto (OCR):** Se aplica OCR a cada imagen de factura para obtener el texto.
3.  **Análisis y Estructuración de Datos:**
    *   El texto de cada factura es analizado para extraer: **Nombre del Cliente** (razón social), **Dirección**, detalles de los productos, y el monto total.
    *   Se guarda una copia de la imagen de la factura en un servicio de almacenamiento en la nube (Cloudinary) y se registra la información en Firestore.
4.  **Integración con la Base de Datos de Clientes:**
    *   Al igual que con los informes, el `CustomerService` busca un cliente por **dirección**.
    *   **Si el cliente no existe**, se crea un nuevo registro con su dirección, coordenadas y el **nombre del cliente** (razón social).
    *   **Si el cliente ya existe**, simplemente se actualiza el campo **nombre del cliente** en el registro existente.

---

## Flujo de Datos y Librerías Clave

El sistema utiliza un conjunto de librerías especializadas para manejar el flujo de datos desde el archivo hasta la base de datos.

-   **Entrada de Archivos (API):**
    -   `Flask`: Es el micro-framework web sobre el que se construye la API REST para recibir las peticiones de carga de archivos.

-   **Procesamiento de Archivos:**
    -   `pdf2image`: Convierte las páginas de los archivos PDF en imágenes que pueden ser procesadas por el motor de OCR.
    -   `Pillow`: Se utiliza para la manipulación básica de imágenes antes del proceso de OCR.

-   **Extracción de Texto (OCR):**
    -   `pytesseract`: Es el conector de Python para el motor **Tesseract OCR**, que se encarga de "leer" el texto de las imágenes.

-   **Análisis y Extracción de Datos:**
    -   `re` (Módulo de Expresiones Regulares): Es fundamental en todo el sistema. Se usa intensivamente para definir patrones de búsqueda y extraer los datos estructurados (nombres, direcciones, etc.) desde el texto crudo devuelto por Tesseract.

-   **Geocodificación:**
    -   `geopy`: Librería que permite conectar con servicios de geocodificación. Se utiliza para convertir las direcciones de los clientes en coordenadas geográficas (latitud y longitud), que son guardadas en la base de datos para evitar futuras llamadas al servicio.

-   **Base de Datos:**
    -   `firebase-admin`: Es el SDK oficial de Google para Python que permite a la aplicación comunicarse de forma segura con **Firestore**, la base de datos NoSQL donde se almacenan todos los registros de clientes y facturas.

-   **Almacenamiento en la Nube:**
    -   `cloudinary`: Se utiliza para subir y almacenar las imágenes originales de las facturas, permitiendo un acceso futuro a ellas a través de una URL.

---

## Estructura del Proyecto

A continuación, se describe brevemente la responsabilidad de cada módulo principal:

-   `app.py`: Punto de entrada de la aplicación Flask.
-   `routes.py`: Define los endpoints de la API (`/process_invoice`, `/process_delivery_report`, etc.).
-   `shared_utils.py`: Contiene funciones de utilidad compartidas por todo el sistema, como la conexión a Firebase, la geocodificación y la extracción de texto.
-   `delivery_parser.py`: Contiene la lógica de parsing especializada para los informes de reparto.
-   `invoice_service.py`: Orquesta el procesamiento de las facturas (OCR, parsing, guardado).
-   `delivery_service.py`: Orquesta el procesamiento de los informes de reparto.
-   `customer_service.py`: Encapsula toda la lógica de negocio para la gestión de clientes en Firestore (crear, buscar, actualizar).
