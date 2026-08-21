/** Block and BlockIO schema types. */

import type { CredentialsProviderName, CredentialsType } from "./types-credentials";

export enum SubmissionStatus {
  DRAFT = "DRAFT",
  PENDING = "PENDING",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
}
export type ReviewSubmissionRequest = {
  store_listing_version_id: string;
  is_approved: boolean;
  comments: string; // External comments visible to creator
  internal_comments?: string; // Admin-only comments
};
export type Category = {
  category: string;
  description: string;
};

export enum BlockCostType {
  RUN = "run",
  BYTE = "byte",
  SECOND = "second",
}

export type BlockCost = {
  cost_amount: number;
  cost_type: BlockCostType;
  cost_filter: Record<string, any>;
};

/* Mirror of backend/data/block.py:Block */
export type Block = {
  id: string;
  name: string;
  description: string;
  categories: Category[];
  inputSchema: BlockIORootSchema;
  outputSchema: BlockIORootSchema;
  staticOutput: boolean;
  uiType: BlockUIType;
  costs: BlockCost[];
};

export type BlockIORootSchema = {
  type: "object";
  properties: Record<string, BlockIOSubSchema>;
  required?: (keyof BlockIORootSchema["properties"])[];
  additionalProperties?: { type: string };
};

export type BlockIOSubSchema =
  | BlockIOSimpleTypeSubSchema
  | BlockIOCombinedTypeSubSchema;

export type BlockIOSubType = BlockIOSimpleTypeSubSchema["type"];

export type BlockIOSimpleTypeSubSchema =
  | BlockIOObjectSubSchema
  | BlockIOCredentialsSubSchema
  | BlockIOKVSubSchema
  | BlockIOArraySubSchema
  | BlockIOTableSubSchema
  | BlockIOStringSubSchema
  | BlockIONumberSubSchema
  | BlockIOBooleanSubSchema
  | BlockIONullSubSchema;

export enum DataType {
  SHORT_TEXT = "short-text",
  LONG_TEXT = "long-text",
  NUMBER = "number",
  DATE = "date",
  TIME = "time",
  DATE_TIME = "date-time",
  FILE = "file",
  SELECT = "select",
  MULTI_SELECT = "multi-select",
  BOOLEAN = "boolean",
  CREDENTIALS = "credentials",
  OBJECT = "object",
  KEY_VALUE = "key-value",
  ARRAY = "array",
  TABLE = "table",
}

export type BlockIOSubSchemaMeta = {
  title?: string;
  description?: string;
  placeholder?: string;
  advanced?: boolean;
  depends_on?: string[];
  hidden?: boolean;
};

export type BlockIOObjectSubSchema = BlockIOSubSchemaMeta & {
  type: "object";
  properties: Record<string, BlockIOSubSchema>;
  const?: Record<keyof BlockIOObjectSubSchema["properties"], any>;
  default?: Record<keyof BlockIOObjectSubSchema["properties"], any>;
  required?: (keyof BlockIOObjectSubSchema["properties"])[];
  secret?: boolean;
};

export type BlockIOKVSubSchema = BlockIOSubSchemaMeta & {
  type: "object";
  additionalProperties?: { type: "string" | "number" | "integer" };
  const?: Record<string, string | number>;
  default?: Record<string, string | number>;
  secret?: boolean;
};

export type BlockIOArraySubSchema = BlockIOSubSchemaMeta & {
  type: "array";
  items?: BlockIOSimpleTypeSubSchema;
  const?: Array<string>;
  default?: Array<string>;
  secret?: boolean;
};

// Table cell values are typically primitives
export type TableCellValue = string | number | boolean | null;

export type TableRow = Record<string, TableCellValue>;

export type BlockIOTableSubSchema = BlockIOSubSchemaMeta & {
  type: "array";
  format: "table";
  items: BlockIOObjectSubSchema;
  const?: TableRow[];
  default?: TableRow[];
  secret?: boolean;
};

export type BlockIOStringSubSchema = BlockIOSubSchemaMeta & {
  type: "string";
  enum?: string[];
  secret?: true;
  const?: string;
  default?: string;
  format?: string;
  maxLength?: number;
};

export type BlockIONumberSubSchema = BlockIOSubSchemaMeta & {
  type: "integer" | "number";
  const?: number;
  default?: number;
  secret?: boolean;
};

export type BlockIOBooleanSubSchema = BlockIOSubSchemaMeta & {
  type: "boolean";
  const?: boolean;
  default?: boolean;
  secret?: boolean;
};

export type BlockIOCredentialsSubSchema = BlockIOObjectSubSchema & {
  /* Mirror of backend/data/model.py:CredentialsFieldSchemaExtra */
  credentials_provider: CredentialsProviderName[];
  credentials_scopes?: string[];
  credentials_types: Array<CredentialsType>;
  discriminator?: string;
  discriminator_mapping?: Record<string, CredentialsProviderName>;
  discriminator_values?: any[];
  secret?: boolean;
};

export type BlockIONullSubSchema = BlockIOSubSchemaMeta & {
  type: "null";
  const?: null;
  secret?: boolean;
};

// At the time of writing, combined schemas only occur on the first nested level in a
// block schema. It is typed this way to make the use of these objects less tedious.
type BlockIOCombinedTypeSubSchema = BlockIOSubSchemaMeta & {
  type: never;
  const: never;
} & (
    | {
        allOf: [BlockIOSimpleTypeSubSchema];
        secret?: boolean;
      }
    | {
        anyOf: BlockIOSimpleTypeSubSchema[];
        default?: string | number | boolean | null;
        secret?: boolean;
        format?: string; // For table format and other formats on anyOf schemas
      }
    | BlockIOOneOfSubSchema
    | BlockIODiscriminatedOneOfSubSchema
  );

export type BlockIOOneOfSubSchema = {
  oneOf: BlockIOSimpleTypeSubSchema[];
  default?: string | number | boolean | null;
  secret?: boolean;
};

export type BlockIODiscriminatedOneOfSubSchema = {
  oneOf: BlockIOObjectSubSchema[];
  discriminator: {
    propertyName: string;
    mapping: Record<string, BlockIOObjectSubSchema>;
  };
  default?: Record<string, any>;
  secret?: boolean;
};

