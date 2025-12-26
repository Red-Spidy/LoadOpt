import axios from 'axios';

// Use empty string to leverage Vite's proxy configuration
// This avoids CORS issues in development
const API_URL = '';

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !window.location.pathname.includes('/login')) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  login: async (username: string, password: string) => {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return response.data;
  },
  
  signup: async (data: { email: string; username: string; password: string; full_name?: string }) => {
    const response = await api.post('/auth/signup', data);
    return response.data;
  },
  
  getMe: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },
};

// Projects API
export const projectsAPI = {
  list: async () => {
    const response = await api.get('/projects/');
    return response.data;
  },
  
  get: async (id: number) => {
    const response = await api.get(`/projects/${id}`);
    return response.data;
  },
  
  create: async (data: { name: string; description?: string }) => {
    const response = await api.post('/projects/', data);
    return response.data;
  },
  
  update: async (id: number, data: { name?: string; description?: string }) => {
    const response = await api.put(`/projects/${id}`, data);
    return response.data;
  },
  
  delete: async (id: number) => {
    await api.delete(`/projects/${id}`);
  },
};

// SKUs API
export const skusAPI = {
  list: async (projectId: number) => {
    const response = await api.get(`/skus/project/${projectId}`);
    return response.data;
  },
  
  get: async (id: number) => {
    const response = await api.get(`/skus/${id}`);
    return response.data;
  },
  
  create: async (data: any) => {
    const response = await api.post('/skus/', data);
    return response.data;
  },
  
  bulkCreate: async (projectId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post(`/skus/bulk?project_id=${projectId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  
  update: async (id: number, data: any) => {
    const response = await api.put(`/skus/${id}`, data);
    return response.data;
  },

  updateQuantity: async (id: number, quantity: number) => {
    const response = await api.patch(`/skus/${id}/quantity?quantity=${quantity}`);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/skus/${id}`);
  },
};

// Containers API
export const containersAPI = {
  list: async (projectId: number) => {
    const response = await api.get(`/containers/project/${projectId}`);
    return response.data;
  },
  
  get: async (id: number) => {
    const response = await api.get(`/containers/${id}`);
    return response.data;
  },
  
  create: async (data: any) => {
    const response = await api.post('/containers/', data);
    return response.data;
  },
  
  update: async (id: number, data: any) => {
    const response = await api.put(`/containers/${id}`, data);
    return response.data;
  },
  
  delete: async (id: number) => {
    await api.delete(`/containers/${id}`);
  },
};

// Plans API
export const plansAPI = {
  list: async (projectId: number) => {
    const response = await api.get(`/plans/project/${projectId}`);
    return response.data;
  },
  
  get: async (id: number) => {
    const response = await api.get(`/plans/${id}`);
    return response.data;
  },
  
  create: async (data: any) => {
    const response = await api.post('/plans/', data);
    return response.data;
  },
  
  update: async (id: number, data: any) => {
    const response = await api.put(`/plans/${id}`, data);
    return response.data;
  },
  
  optimize: async (id: number) => {
    const response = await api.post(`/plans/${id}/optimize`);
    return response.data;
  },
  
  delete: async (id: number) => {
    await api.delete(`/plans/${id}`);
  },
  
  exportCSV: async (id: number) => {
    const response = await api.get(`/plans/${id}/export/csv`, {
      responseType: 'blob',
    });
    return response.data;
  },
  
  getSummary: async (id: number) => {
    const response = await api.get(`/plans/${id}/export/summary`);
    return response.data;
  },
};

// Delivery Groups API
export const deliveryGroupsAPI = {
  list: async (projectId: number) => {
    const response = await api.get(`/delivery-groups/project/${projectId}`);
    return response.data;
  },
  
  get: async (id: number) => {
    const response = await api.get(`/delivery-groups/${id}`);
    return response.data;
  },
  
  create: async (data: { project_id: number; name: string; color?: string; delivery_order: number }) => {
    const response = await api.post('/delivery-groups/', data);
    return response.data;
  },
  
  update: async (id: number, data: { name?: string; color?: string; delivery_order?: number }) => {
    const response = await api.put(`/delivery-groups/${id}`, data);
    return response.data;
  },
  
  delete: async (id: number) => {
    await api.delete(`/delivery-groups/${id}`);
  },
  
  assignSKUs: async (groupId: number, skuIds: number[]) => {
    const response = await api.post(`/delivery-groups/${groupId}/assign-skus`, skuIds);
    return response.data;
  },
  
  removeSKUs: async (groupId: number, skuIds: number[]) => {
    const response = await api.post(`/delivery-groups/${groupId}/remove-skus`, skuIds);
    return response.data;
  },
};
