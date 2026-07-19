// frontend/nepali-voice-ui/src/app/services/auth.interceptor.ts
//
// Beginner explanation:
// This file automatically adds the login token to backend HTTP requests.
//
// Without this interceptor, every service method would have to manually add:
//
//   Authorization: Bearer <token>
//
// With this interceptor, Angular adds it automatically.

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const authService = inject(AuthService);
  const token = authService.getAccessToken();

  if (!token) {
    return next(request);
  }

  const authenticatedRequest = request.clone({
    setHeaders: {
      Authorization: `Bearer ${token}`
    }
  });

  return next(authenticatedRequest);
};