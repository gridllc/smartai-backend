import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
    baseURL: API_BASE_URL,
    withCredentials: true, // send cookies like refresh_token
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 10000,
});


// Request Interceptor: Adds the auth token to every outgoing request
apiClient.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('accessToken');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response Interceptor: This is where the magic happens. It catches 401 errors.
apiClient.interceptors.response.use(
    // If the response is successful (e.g., status 200), just return it
    (response) => {
        return response;
    },
    // If the response is an error...
    async (error) => {
        const originalRequest = error.config;

        // Check if it's a 401 error and we haven't already tried to refresh
        if (error.response.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true; // Mark that we've tried to refresh once

            try {
                // Call the refresh token endpoint
                const { data } = await apiClient.post('/api/auth/refresh-token');

                // Update the access token in localStorage
                localStorage.setItem('accessToken', data.access_token);

                // Update the authorization header for the original request
                apiClient.defaults.headers.common['Authorization'] = 'Bearer ' + data.access_token;

                // Retry the original request with the new token
                return apiClient(originalRequest);

            } catch (refreshError) {
                // If refreshing fails, the user's session is truly expired.
                // Log them out and reject the promise.
                console.error("Session expired. Please log in again.");
                localStorage.removeItem('accessToken');
                // You would typically redirect to the login page here
                // window.location.href = '/login'; 
                return Promise.reject(refreshError);
            }
        }

        // For any other errors, just pass them along
        return Promise.reject(error);
    }
);

export default apiClient;