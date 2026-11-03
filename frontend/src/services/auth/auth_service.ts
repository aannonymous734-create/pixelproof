import type { AuthResponse, LoginCredentials, RegisterData, User } from "@/models/AuthModels";
import api from "../apiClients";

export const login = async (credentials: LoginCredentials): Promise<AuthResponse> => {
  const response = await api.post("/auth/login", credentials);
  return response.data;
};

export const register = async (userData: RegisterData): Promise<{ data: User; message: string }> => {
  const response = await api.post("/auth/register", userData);
  return response.data;
};

export const logout = async (): Promise<void> => {
  await api.post("/logout");
};

export const getCurrentUser = async (): Promise<User> => {
  const response = await api.get("/me");
  return response.data.user;
};
