"use client";

import React, { createContext, useContext, useEffect, useState, useMemo } from "react";
import {
  fetchAvailableModels,
  fetchModelSetting,
  updateModelSetting,
  fetchGuardianSetting,
  updateGuardianSetting,
  type AvailableModelItem,
} from "@/lib/api";
import { FALLBACK_MODELS } from "@/lib/models-fallback";

const STORAGE_KEY = "querylens_selected_model";
const GUARDIAN_STORAGE_KEY = "querylens_guardian_mode";
const CREDIT_PRICE_USD = 0.002; // $2.00 = 1,000 Credits
const GUARDIAN_CREDIT_FEE = 5;

interface ModelContextType {
  availableModels: AvailableModelItem[];
  selectedModel: string;
  selectedModelInfo: AvailableModelItem | null;
  defaultModelId: string;
  guardianMode: boolean;
  setGuardianMode: (enabled: boolean) => Promise<void>;
  guardianCreditFee: number;
  loading: boolean;
  isModelModalOpen: boolean;
  openModelModal: () => void;
  closeModelModal: () => void;
  isSettingsOpen: boolean;
  openSettings: () => void;
  closeSettings: () => void;
  setSelectedModel: (modelId: string) => Promise<void>;
  calculateCost: (baseCredits: number, modelId?: string, guardian?: boolean) => {
    totalCredits: number;
    modelDelta: number;
    guardianFee: number;
    guardianDiscount: number;
    costUsd: number;
    costUsdFormatted: string;
    modelCost: number;
  };
}

const ModelContext = createContext<ModelContextType | undefined>(undefined);

export function ModelProvider({ children }: { children: React.ReactNode }) {
  const [availableModels, setAvailableModels] = useState<AvailableModelItem[]>(FALLBACK_MODELS);
  const [selectedModel, setSelectedModelState] = useState<string>("gpt-4o-mini");
  const [defaultModelId, setDefaultModelId] = useState<string>("gpt-4o-mini");
  const [guardianMode, setGuardianState] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [isModelModalOpen, setIsModelModalOpen] = useState<boolean>(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;

    async function loadModelsAndSettings() {
      try {
        const [modelsRes, settingRes, guardianRes] = await Promise.allSettled([
          fetchAvailableModels(),
          fetchModelSetting(),
          fetchGuardianSetting(),
        ]);

        let loadedModels: AvailableModelItem[] = FALLBACK_MODELS;
        let serverDefault = "gpt-4o-mini";

        if (modelsRes.status === "fulfilled" && modelsRes.value?.data?.length) {
          loadedModels = modelsRes.value.data;
          serverDefault = modelsRes.value.default_model || "gpt-4o-mini";
          if (isMounted) {
            setAvailableModels(loadedModels);
            setDefaultModelId(serverDefault);
          }
        }

        let initialChosen = serverDefault;

        // Check localStorage first
        const savedLocal = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
        if (savedLocal && loadedModels.some((m) => m.id === savedLocal)) {
          initialChosen = savedLocal;
        } else if (settingRes.status === "fulfilled") {
          const s = settingRes.value;
          const serverModel = s.currentModel || s.current_model;
          if (serverModel && loadedModels.some((m) => m.id === serverModel)) {
            initialChosen = serverModel;
          }
        }

        let initialGuardian = true;
        const savedGuardian = typeof window !== "undefined" ? localStorage.getItem(GUARDIAN_STORAGE_KEY) : null;
        if (savedGuardian !== null) {
          initialGuardian = savedGuardian === "true";
        } else if (guardianRes.status === "fulfilled") {
          initialGuardian = guardianRes.value.guardian;
        }

        if (isMounted) {
          setSelectedModelState(initialChosen);
          setGuardianState(initialGuardian);
        }
      } catch (err) {
        console.error("Failed to load models configuration:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadModelsAndSettings();

    return () => {
      isMounted = false;
    };
  }, []);

  const selectedModelInfo = useMemo(() => {
    if (!availableModels.length) return null;
    return availableModels.find((m) => m.id === selectedModel) || availableModels[0];
  }, [availableModels, selectedModel]);

  const setSelectedModel = async (modelId: string) => {
    setSelectedModelState(modelId);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, modelId);
    }
    try {
      await updateModelSetting(modelId);
    } catch {
      // Keep local state if network fails
    }
  };

  const setGuardianMode = async (enabled: boolean) => {
    setGuardianState(enabled);
    if (typeof window !== "undefined") {
      localStorage.setItem(GUARDIAN_STORAGE_KEY, String(enabled));
    }
    try {
      await updateGuardianSetting(enabled);
    } catch {
      // Keep local state if network fails
    }
  };

  const calculateCost = (baseCredits: number, modelId?: string, guardian?: boolean) => {
    const targetId = modelId || selectedModel;
    const isGuardian = guardian !== undefined ? guardian : guardianMode;
    const model = availableModels.find((m) => m.id === targetId);
    const defaultModel = availableModels.find((m) => m.id === defaultModelId) || { credit_cost: 5 };
    const modelCost = model ? model.credit_cost : 5;
    const baselineCost = defaultModel.credit_cost || 5;
    const modelDelta = modelCost - baselineCost;

    const rawTotal = Math.max(1, baseCredits + modelDelta);
    let guardianDiscount = 0;
    let totalCredits = rawTotal;

    if (!isGuardian) {
      guardianDiscount = Math.min(GUARDIAN_CREDIT_FEE, Math.max(0, rawTotal - 1));
      totalCredits = Math.max(1, rawTotal - guardianDiscount);
    }

    const costUsd = totalCredits * CREDIT_PRICE_USD;
    const costUsdFormatted = `$${costUsd.toFixed(3)}`;

    return {
      totalCredits,
      modelDelta,
      guardianFee: isGuardian ? GUARDIAN_CREDIT_FEE : 0,
      guardianDiscount,
      costUsd,
      costUsdFormatted,
      modelCost,
    };
  };

  const value = {
    availableModels,
    selectedModel,
    selectedModelInfo,
    defaultModelId,
    guardianMode,
    setGuardianMode,
    guardianCreditFee: GUARDIAN_CREDIT_FEE,
    loading,
    isModelModalOpen,
    openModelModal: () => setIsModelModalOpen(true),
    closeModelModal: () => setIsModelModalOpen(false),
    isSettingsOpen,
    openSettings: () => setIsSettingsOpen(true),
    closeSettings: () => setIsSettingsOpen(false),
    setSelectedModel,
    calculateCost,
  };

  return <ModelContext.Provider value={value}>{children}</ModelContext.Provider>;
}

export function useModelSettings() {
  const context = useContext(ModelContext);
  if (!context) {
    throw new Error("useModelSettings must be used within a ModelProvider");
  }
  return context;
}

