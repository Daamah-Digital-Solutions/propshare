import { createContext, useContext, useState, ReactNode } from "react";

interface ReinvestState {
  isReinvesting: boolean;
  reinvestAmount: number;
  discountPercentage: number;
  discountAmount: number;
  netInvestmentValue: number;
  isFamilyReinvest: boolean;
}

interface ReinvestContextType {
  reinvestState: ReinvestState;
  setReinvestment: (amount: number, discountRate?: number) => void;
  setFamilyReinvestment: (amount: number, totalDiscount: number) => void;
  clearReinvestment: () => void;
  applyReinvestDiscount: (baseAmount: number) => {
    originalAmount: number;
    discountAmount: number;
    netAmount: number;
  };
}

const REINVEST_DISCOUNT_RATE = 0.05; // 5% discount

const defaultState: ReinvestState = {
  isReinvesting: false,
  reinvestAmount: 0,
  discountPercentage: 5,
  discountAmount: 0,
  netInvestmentValue: 0,
  isFamilyReinvest: false,
};

const ReinvestContext = createContext<ReinvestContextType | undefined>(undefined);

export const ReinvestProvider = ({ children }: { children: ReactNode }) => {
  const [reinvestState, setReinvestState] = useState<ReinvestState>(defaultState);

  const setReinvestment = (amount: number, discountRate: number = REINVEST_DISCOUNT_RATE) => {
    const discountAmount = amount * discountRate;
    const netInvestmentValue = amount + discountAmount; // The actual investment value they get
    
    setReinvestState({
      isReinvesting: true,
      reinvestAmount: amount,
      discountPercentage: discountRate * 100,
      discountAmount: discountAmount,
      netInvestmentValue: netInvestmentValue,
      isFamilyReinvest: false,
    });
  };

  const setFamilyReinvestment = (amount: number, totalDiscount: number) => {
    const discountRate = totalDiscount / 100;
    const discountAmount = amount * discountRate;
    const netInvestmentValue = amount + discountAmount;
    
    setReinvestState({
      isReinvesting: true,
      reinvestAmount: amount,
      discountPercentage: totalDiscount,
      discountAmount: discountAmount,
      netInvestmentValue: netInvestmentValue,
      isFamilyReinvest: true,
    });
  };

  const clearReinvestment = () => {
    setReinvestState(defaultState);
  };

  const applyReinvestDiscount = (baseAmount: number) => {
    if (!reinvestState.isReinvesting) {
      return {
        originalAmount: baseAmount,
        discountAmount: 0,
        netAmount: baseAmount,
      };
    }
    
    const discountRate = reinvestState.discountPercentage / 100;
    const discountAmount = baseAmount * discountRate;
    return {
      originalAmount: baseAmount,
      discountAmount: discountAmount,
      netAmount: baseAmount - discountAmount,
    };
  };

  return (
    <ReinvestContext.Provider value={{
      reinvestState,
      setReinvestment,
      setFamilyReinvestment,
      clearReinvestment,
      applyReinvestDiscount,
    }}>
      {children}
    </ReinvestContext.Provider>
  );
};

export const useReinvest = () => {
  const context = useContext(ReinvestContext);
  if (!context) {
    throw new Error("useReinvest must be used within ReinvestProvider");
  }
  return context;
};
