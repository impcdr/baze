import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { MockDb } from './mock-db';

/** Serves `/api/*` from the in-memory shelf. Anything else goes to the network. */
export const mockApiInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith('/api/')) return next(req);
  return inject(MockDb).handle(req);
};
