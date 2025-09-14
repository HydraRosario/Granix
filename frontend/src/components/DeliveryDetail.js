import React from 'react';
import './DeliveryDetail.css';

const DeliveryDetail = ({ delivery, onClose, onMarkAsCompleted }) => {
  if (!delivery) {
    return null;
  }

  const formatCurrency = (amount) => {
    const number = Number(amount);
    return new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: 'ARS',
    }).format(number || 0);
  };

  const handlePayment = (type) => {
    alert(`Payment registered as: ${type}`);
    // We could also call a function passed via props here
  };

  const handleComplete = () => {
    onMarkAsCompleted(delivery.id);
    onClose();
  };

  const formattedTotalAmount = formatCurrency(delivery.parsed_data.total_amount);

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <button className="close-button" onClick={onClose}>X</button>
        <h2>Detalles de Entrega</h2>
        <h3>{delivery.client_name || 'Cliente no encontrado'}</h3>
        <p>{delivery.parsed_data?.address || 'Dirección no encontrada'}</p>

        <h4>Artículos:</h4>
        <table className="product-items-table">
          <thead>
            <tr>
              <th>Artículo</th>
              <th>Cantidad</th>
              <th>Descripción</th>
              <th>Precio</th>
            </tr>
          </thead>
          <tbody>
            {(delivery.product_items || []).map((item, idx) => (
              <tr key={idx}>
                <td>{item.product_code}</td>
                <td>{item.quantity}</td>
                <td>{item.description}</td>
                <td>{formatCurrency(item.item_total)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan="3" style={{ textAlign: 'right' }}><strong>IMPORTE TOTAL:</strong></td>
              <td>{formattedTotalAmount}</td>
            </tr>
          </tfoot>
        </table>

        <div>
          <button onClick={() => handlePayment('cash')}>Pagar en Efectivo</button>
          <button onClick={() => handlePayment('card')}>Pagar con Tarjeta</button>
          <button onClick={handleComplete} disabled={delivery.completed}>
            {delivery.completed ? 'Completado' : 'Marcar como Completado'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeliveryDetail;