const mongoose = require('mongoose');

const FactFinancialStatementSchema = new mongoose.Schema(
  {
    stock_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimStock',
      required: true
    },
    report_period_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimReportPeriod',
      required: true
    },
    data_source_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'DimStockDataSource',
      required: true
    },

    //# Doanh thu / Lợi nhuận
    net_revenue: {
      type: Number
    },
    gross_profit: {
      type: Number
    },
    net_profit_from_operating_activities: {
      type: Number
    },
    corporate_income_tax: {
      type: Number
    },
    profit_before_tax: {
      type: Number
    },
    profit_after_tax: {
      type: Number
    },
    parent_company_profit: {
      type: Number
    },

    //# Tài sản / Nợ
    current_assets: {
      type: Number
    },
    total_assets: {
      type: Number
    },
    liabilities: {
      type: Number
    },
    current_liabilities: {
      type: Number
    },
    equity: {
      type: Number
    },

    //# Ngân hàng / Tài chính đặc thù
    net_interest_income: {
      type: Number
    },
    operating_expense: {
      type: Number
    },
    total_operating_income: {
      type: Number
    },
    customer_loans: {
      type: Number
    },
    customer_deposits: {
      type: Number
    },
    retained_earnings: {
      type: Number
    },

    //# Định giá & Hiệu quả
    eps: {
      type: Number
    },
    pe: {
      type: Number
    },
    forward_pe: {
      type: Number
    },
    bvps: {
      type: Number
    },
    pb: {
      type: Number
    },
    beta: {
      type: Number
    },
    ros: {
      type: Number
    },
    roe: {
      type: Number
    },
    roaa: {
      type: Number
    },

    crawled_at: {
      type: Date,
      default: Date.now
    }
  },
  {
    timestamps: {
      createdAt: 'created_at',
      updatedAt: false
    },
    collection: 'factFinancialStatements'
  }
);

FactFinancialStatementSchema.index({ stock_id: 1, report_period_id: 1, data_source_id: 1 }, { unique: true });

module.exports = mongoose.model('FactFinancialStatement', FactFinancialStatementSchema);
