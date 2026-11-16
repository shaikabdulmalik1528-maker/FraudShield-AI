import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Interceptor to attach JWT token if present in localStorage
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('fraudshield_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Authentication APIs
export const login = async (username, password) => {
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);
  const response = await axios.post(`${API_BASE_URL}/api/v1/auth/login`, params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return response.data;
};

export const getCurrentUser = async () => {
  const response = await apiClient.get('/auth/me');
  return response.data;
};

// Analytics APIs
export const getOverviewStats = async () => {
  const response = await apiClient.get('/analytics/overview');
  return response.data;
};

export const getFraudTrends = async () => {
  const response = await apiClient.get('/analytics/fraud-trends');
  return response.data;
};

export const getRiskDistribution = async () => {
  const response = await apiClient.get('/analytics/risk-distribution');
  return response.data;
};

export const getModelPerformance = async () => {
  const response = await apiClient.get('/analytics/model-performance');
  return response.data;
};

// Prediction APIs
export const predictTransaction = async (transactionData) => {
  const response = await apiClient.post('/predict', transactionData);
  return response.data;
};

// Transactions APIs
export const getTransactions = async (params = {}) => {
  const response = await apiClient.get('/transactions', { params });
  return response.data;
};

export const getTransactionById = async (id) => {
  const response = await apiClient.get(`/transactions/${id}`);
  return response.data;
};

export const getTransactionExplanation = async (id) => {
  const response = await apiClient.get(`/explanations/${id}`);
  return response.data;
};

// Alerts APIs
export const getAlerts = async (status = null) => {
  const params = status ? { status } : {};
  const response = await apiClient.get('/alerts', { params });
  return response.data;
};

export const updateAlertStatus = async (alertId, updateData) => {
  const response = await apiClient.patch(`/alerts/${alertId}`, updateData);
  return response.data;
};

// Model info & Config APIs
export const getModelInfo = async () => {
  const response = await apiClient.get('/model/info');
  return response.data;
};

export const updateThreshold = async (threshold) => {
  const response = await apiClient.post('/model/threshold', { threshold });
  return response.data;
};

// Health Check
export const getSystemHealth = async () => {
  const response = await axios.get(`${API_BASE_URL}/health`);
  return response.data;
};

export default apiClient;
