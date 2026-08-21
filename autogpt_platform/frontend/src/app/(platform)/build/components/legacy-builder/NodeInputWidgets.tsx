/** Legacy builder input field widgets. */
import { Calendar } from "@/components/__legacy__/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/__legacy__/ui/popover";
import { format } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { beautifyString, cn } from "@/lib/utils";
import { Node, useNodeId, useNodesData } from "@xyflow/react";
import {
  ConnectionData,
  CustomNodeData,
} from "@/app/(platform)/build/components/legacy-builder/CustomNode/CustomNode";
import { Cross2Icon, Pencil2Icon, PlusIcon } from "@radix-ui/react-icons";
import {
  BlockIOArraySubSchema,
  BlockIOBooleanSubSchema,
  BlockIOCredentialsSubSchema,
  BlockIODiscriminatedOneOfSubSchema,
  BlockIOKVSubSchema,
  BlockIONumberSubSchema,
  BlockIOObjectSubSchema,
  BlockIORootSchema,
  BlockIOSimpleTypeSubSchema,
  BlockIOStringSubSchema,
  BlockIOSubSchema,
  BlockIOTableSubSchema,
  DataType,
  determineDataType,
} from "@/lib/autogpt-server-api/types";
import React, {
  FC,
  useCallback,
  useEffect,
  useMemo,
  useState,
  useRef,
} from "react";
import { Button } from "../../../../../components/__legacy__/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../../../components/__legacy__/ui/select";
import {
  MultiSelector,
  MultiSelectorContent,
  MultiSelectorInput,
  MultiSelectorItem,
  MultiSelectorList,
  MultiSelectorTrigger,
} from "../../../../../components/__legacy__/ui/multiselect";
import { LocalValuedInput } from "../../../../../components/__legacy__/ui/input";
import NodeHandle from "./NodeHandle";
import { CredentialsInput } from "@/app/(platform)/library/agents/[id]/components/AgentRunsView/components/CredentialsInputs/CredentialsInputs";
import { Switch } from "../../../../../components/atoms/Switch/Switch";
import { NodeTableInput } from "../../../../../components/node-table-input";

export type NodeObjectInputTreeProps = {
  nodeId: string;
  selfKey?: string;
  schema: BlockIORootSchema | BlockIOObjectSubSchema;
  object?: { [key: string]: any };
  connections: ConnectionData;
  handleInputClick: (key: string) => void;
  handleInputChange: (key: string, value: any) => void;
  errors: { [key: string]: string | undefined };
  className?: string;
  displayName?: string;
};

export const NodeDateTimeInput: FC<{
  selfKey: string;
  schema: BlockIOStringSubSchema;
  value?: string;
  error?: string;
  handleInputChange: NodeObjectInputTreeProps["handleInputChange"];
  className?: string;
  displayName: string;
  hideDate?: boolean;
  hideTime?: boolean;
}> = ({
  selfKey,
  value = "",
  error,
  handleInputChange,
  className,
  hideDate = false,
  hideTime = false,
}) => {
  const dateInput = value && !hideDate ? new Date(value) : new Date();
  const timeInput = value && !hideTime ? format(dateInput, "HH:mm") : "00:00";

  const handleDateSelect = (newDate: Date | undefined) => {
    if (!newDate) return;

    if (hideTime) {
      // Only pass YYYY-MM-DD if time is hidden
      handleInputChange(selfKey, format(newDate, "yyyy-MM-dd"));
    } else {
      // Otherwise pass full date/time, but still incorporate time
      const [hours, minutes] = timeInput.split(":").map(Number);
      newDate.setHours(hours, minutes);
      handleInputChange(selfKey, newDate.toISOString());
    }
  };

  const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = e.target.value;

    if (hideDate) {
      // Only pass HH:mm if date is hidden
      handleInputChange(selfKey, newTime);
    } else {
      // Otherwise pass full date/time
      const [hours, minutes] = newTime.split(":").map(Number);
      dateInput.setHours(hours, minutes);
      handleInputChange(selfKey, dateInput.toISOString());
    }
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {hideDate || (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={cn(
                "w-full justify-start text-left font-normal",
                !value && "text-muted-foreground",
              )}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {value && dateInput ? (
                format(dateInput, "PPP")
              ) : (
                <span>Pick a date</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="single"
              selected={dateInput}
              onSelect={handleDateSelect}
              autoFocus
            />
          </PopoverContent>
        </Popover>
      )}
      {hideTime || (
        <LocalValuedInput
          type="time"
          value={timeInput}
          onChange={handleTimeChange}
          className="w-full"
        />
      )}
      {error && <span className="error-message">{error}</span>}
    </div>
  );
};

export const NodeFileInput: FC<{
  selfKey: string;
  schema: BlockIOStringSubSchema;
  value?: string;
  error?: string;
  handleInputChange: NodeObjectInputTreeProps["handleInputChange"];
  className?: string;
  displayName: string;
}> = ({
  selfKey,
  value = "",
  error,
  handleInputChange,
  className,
  displayName,
}) => {
  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (e) => {
        const base64String = e.target?.result as string;
        handleInputChange(selfKey, base64String);
      };
      reader.readAsDataURL(file);
    },
    [selfKey, handleInputChange],
  );

  const getFileLabel = useCallback((value: string) => {
    if (value.startsWith("data:")) {
      const matches = value.match(/^data:([^;]+);/);
      if (matches?.[1]) {
        const mimeParts = matches[1].split("/");
        if (mimeParts.length > 1) {
          return `${mimeParts[1].toUpperCase()} file`;
        }
        return `${matches[1]} file`;
      }
    } else {
      const pathParts = value.split(".");
      if (pathParts.length > 1) {
        const ext = pathParts.pop();
        if (ext) return `${ext.toUpperCase()} file`;
      }
    }
    return "File";
  }, []);

  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="nodrag flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => inputRef.current?.click()}
            className="w-full"
          >
            {value ? `Change ${displayName}` : `Upload ${displayName}`}
          </Button>
          {value && (
            <Button
              variant="ghost"
              className="text-red-500 hover:text-red-700"
              onClick={() => {
                if (inputRef.current) inputRef.current.value = "";
                handleInputChange(selfKey, "");
              }}
            >
              <Cross2Icon className="h-4 w-4" />
            </Button>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="*/*"
          onChange={handleFileChange}
          className="hidden"
        />
        {value && (
          <div className="break-all rounded-md border border-gray-300 p-2 dark:border-gray-600">
            <small>{getFileLabel(value)}</small>
          </div>
        )}
      </div>
      {error && <span className="error-message">{error}</span>}
    </div>
  );
};

export export export const NodeTextBoxInput: FC<{
  selfKey: string;
  schema: BlockIOStringSubSchema;
  value?: string;
  error?: string;
  handleInputChange: NodeObjectInputTreeProps["handleInputChange"];
  handleInputClick: NodeObjectInputTreeProps["handleInputClick"];
  className?: string;
  displayName: string;
}> = ({
  selfKey,
  schema,
  value = "",
  error,
  handleInputChange,
  handleInputClick,
  className,
  displayName,
}) => {
  value ||= schema.default || "";

  const [localValue, setLocalValue] = useState(value || schema.default || "");

  useEffect(() => {
    setLocalValue(value || schema.default || "");
  }, [value, schema.default]);

  return (
    <div className={className}>
      <div
        className="nodrag relative m-0 h-[200px] w-full bg-yellow-100 p-4 dark:bg-yellow-900"
        onClick={schema.secret ? () => handleInputClick(selfKey) : undefined}
      >
        <textarea
          id={selfKey}
          value={schema.secret && localValue ? "********" : localValue}
          onChange={(e) => setLocalValue(e.target.value)}
          onBlur={() => handleInputChange(selfKey, localValue)}
          readOnly={schema.secret}
          placeholder={
            schema?.placeholder || `Enter ${beautifyString(displayName)}`
          }
          className="h-full w-full resize-none overflow-hidden border-none bg-transparent text-lg text-black outline-none dark:text-white"
          style={{
            fontSize: "min(1em, 16px)",
            lineHeight: "1.2",
          }}
        />
      </div>
      {error && <span className="error-message">{error}</span>}
    </div>
  );
};

export const NodeNumberInput: FC<{
  selfKey: string;
  schema: BlockIONumberSubSchema;
  value?: number;
  error?: string;
  handleInputChange: NodeObjectInputTreeProps["handleInputChange"];
  className?: string;
  displayName?: string;
}> = ({
  selfKey,
  schema,
  value,
  error,
  handleInputChange,
  className,
  displayName,
}) => {
  value ||= schema.default;
  displayName ||= schema.title || beautifyString(selfKey);
  return (
    <div className={className}>
      <div className="nodrag flex items-center justify-between space-x-3">
        <LocalValuedInput
          type="number"
          id={selfKey}
          value={value}
          onChange={(e) =>
            handleInputChange(selfKey, parseFloat(e.target.value))
          }
          placeholder={
            schema.placeholder || `Enter ${beautifyString(displayName)}`
          }
          className="dark:text-white"
        />
      </div>
      {error && <span className="error-message">{error}</span>}
    </div>
  );
};

export const NodeBooleanInput: FC<{
  selfKey: string;
  schema: BlockIOBooleanSubSchema;
  value?: boolean;
  error?: string;
  handleInputChange: NodeObjectInputTreeProps["handleInputChange"];
  className?: string;
  displayName: string;
}> = ({ selfKey, schema, value, error, handleInputChange, className }) => {
  if (value == null) {
    value = schema.default ?? false;
  }
  return (
    <div className={className}>
      <Switch
        defaultChecked={value}
        onCheckedChange={(v) => handleInputChange(selfKey, v)}
      />
      {error && <span className="error-message">{error}</span>}
    </div>
  );
};

export const NodeFallbackInput: FC<{
  selfKey: string;
  schema?: BlockIOSubSchema;
  value: any;
  error?: string;
  handleInputChange: NodeObjectInputTreeProps["handleInputChange"];
  handleInputClick: NodeObjectInputTreeProps["handleInputClick"];
  className?: string;
  displayName: string;
}> = ({
  selfKey,
  schema,
  value,
  error,
  handleInputChange,
  handleInputClick,
  className,
  displayName,
}) => {
  value ||= (schema as BlockIOStringSubSchema)?.default;
  return (
    <NodeStringInput
      selfKey={selfKey}
      schema={{ type: "string", ...schema } as BlockIOStringSubSchema}
      value={value}
      error={error}
      handleInputChange={handleInputChange}
      handleInputClick={handleInputClick}
      className={className}
      displayName={displayName}
    />
  );
};
