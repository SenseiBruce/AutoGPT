export type Brand<T, Brand extends string> = T & {
  readonly [B in Brand as `__${B}_brand`]: never;
};

