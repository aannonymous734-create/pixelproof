import { configureStore } from "@reduxjs/toolkit";
import authReducer, { STORAGE_KEY } from "@/AuthStore/slice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
  },
});

store.subscribe(() => {
  if (typeof window === "undefined") return;
  try {
    const { auth } = store.getState();
    if (auth.isAuth) localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
    else localStorage.removeItem(STORAGE_KEY);
  } catch (e) {
    console.error("Failed to save auth state", e);
  }
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
