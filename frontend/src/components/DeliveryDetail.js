import React from 'react';
import './DeliveryDetail.css';

const DeliveryDetail = ({ delivery, onClose, onMarkAsCompleted }) => {
  if (!delivery) {
    return null;
  }

  const handlePayment = (type) => {
    alert(`Payment registered as: ${type}`);
    // We could also call a function passed via props here
  };

  const handleComplete = () => {
    onMarkAsCompleted(delivery.id);
    onClose();
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <button className="close-button" onClick={onClose}>X</button>
        <h2>Delivery Details</h2>
        <h3>{delivery.location_name}</h3>
        <p>{delivery.address}</p>

        <h4>Product Items:</h4>
        <div className="product-items-list">
          {delivery.items.map((item, idx) => (
            <div key={idx} className="product-item-card">
              <p><strong>Description:</strong> {item.description}</p>
              <p><strong>Quantity:</strong> {item.quantity}</p>
              <p><strong>Total:</strong> ${item.item_total ? item.item_total.toFixed(2) : 'N/A'}</p>
            </div>
          ))}
        </div>

        <h4>Total Amount: ${delivery.total_amount}</h4>

        <div>
          <button onClick={() => handlePayment('cash')}>Pay with Cash</button>
          <button onClick={() => handlePayment('card')}>Pay with Card</button>
          <button onClick={handleComplete} disabled={delivery.completed}>
            {delivery.completed ? 'Completed' : 'Mark as Completed'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeliveryDetail;