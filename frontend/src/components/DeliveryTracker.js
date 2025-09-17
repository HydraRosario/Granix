import React, { useState, useEffect } from 'react';
import { useAppContext } from '../context/AppContext';
import './DeliveryTracker.css';

const DeliveryTracker = () => {
    const { optimizedRoute, error } = useAppContext();
    const [currentStopIndex, setCurrentStopIndex] = useState(0);

    // Reset index if the route data changes
    useEffect(() => {
        setCurrentStopIndex(0);
    }, [optimizedRoute]);

    if (error) {
        return <div className="error-message">Error: {error}</div>;
    }

    if (!optimizedRoute || optimizedRoute.length === 0) {
        return (
            <div className="delivery-tracker-container">
                <h2>Seguimiento de Ruta</h2>
                <div className="no-route-message">
                    <p>Aún no se ha procesado una hoja de ruta. 🚚</p>
                    <p>Sube un reporte de entregas para comenzar.</p>
                </div>
            </div>
        );
    }

    const handleNextStop = () => {
        if (currentStopIndex < optimizedRoute.length) {
            setCurrentStopIndex(prevIndex => prevIndex + 1);
        }
    };

    const isRouteComplete = currentStopIndex >= optimizedRoute.length;
    const currentStop = isRouteComplete ? null : optimizedRoute[currentStopIndex];

    // Determine package count. Fallback to 1 if not available.
    const getPackageCount = (stop) => {
        if (stop?.packages) {
            return stop.packages;
        }
        if (stop?.parsed_data?.product_items) {
            return stop.parsed_data.product_items.length;
        }
        return 1; // Default fallback
    };

    return (
        <div className="delivery-tracker-container">
            {/* 1. Barra de Progreso de Paradas */}
            <div className="stops-progress-bar">
                {optimizedRoute.map((_, index) => {
                    let markerClass = 'stop-marker';
                    if (index < currentStopIndex) {
                        markerClass += ' visited';
                    } else if (index === currentStopIndex) {
                        markerClass += ' current';
                    }
                    return <div key={index} className={markerClass}></div>;
                })}
            </div>

            {/* 2. Detalles y Acciones de la Parada Actual */}
            <div className="current-stop-details">
                {isRouteComplete ? (
                    <p className="completion-message">¡Ruta completada!</p>
                ) : (
                    <div className="stop-layout-container"> {/* Nuevo Contenedor Flex */}
                        <div className="stop-info">
                            <h2>{currentStop.commercial_entity || "Cliente no encontrado"}</h2>
                            <p>{currentStop.delivery_address || "Dirección no encontrada"}</p>
                            {/* 
                                Se renderiza la información de entrega adicional.
                                ASUNCIÓN: El campo se llama 'delivery_instructions'.
                                Si el nombre del campo en tus datos es diferente, actualízalo aquí.
                            */}
                            {currentStop.delivery_instructions && (
                                <p className="delivery-instructions">{currentStop.delivery_instructions}</p>
                            )}
                            <p><span className="packages">{getPackageCount(currentStop)}</span> bultos</p>
                        </div>

                        <div className="action-buttons">
                            <button id="btn-delivered" onClick={handleNextStop}>Entregado</button>
                            <button id="btn-undelivered" onClick={handleNextStop}>No se pudo entregar</button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default DeliveryTracker;
