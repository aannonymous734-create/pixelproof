import type { User } from "@/models/AuthModels";
import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";

interface AuthState {
  user: User | null;
  isAuth: boolean;
}

export const STORAGE_KEY = "auth";

// Only the user profile is kept in localStorage; the tokens live in httpOnly cookies set by Laravel.
const loadState = (): AuthState => {
  if (typeof window === "undefined") return { user: null, isAuth: false };
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return JSON.parse(saved) as AuthState;
  } catch (e) {
    console.error("Failed to load auth state", e);
  }
  return { user: null, isAuth: false };
};

const authSlice = createSlice({
  name: "auth",
  initialState: loadState(),
  reducers: {
    LoginUser: (state, action: PayloadAction<{ user: User }>) => {
      state.isAuth = true;
      state.user = action.payload.user;
    },
    LogoutUser: (state) => {
      state.isAuth = false;
      state.user = null;
    },
  },
});

export const { LoginUser, LogoutUser } = authSlice.actions;
export default authSlice.reducer;
