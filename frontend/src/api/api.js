import axios from 'axios';

const API_BASE_URL = 'http://localhost:5000'; // Our Flask backend URL

export const uploadInvoice = async (file) => {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await axios.post(`${API_BASE_URL}/process_invoice`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  } catch (error) {
    console.error('Error uploading invoice:', error);
    // Propagate the error for the context to handle
    throw error;
  }
};
