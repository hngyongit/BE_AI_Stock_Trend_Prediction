const mongoose = require('mongoose');

const FactFinancialReportSourceSchema = new mongoose.Schema(
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
    source_url: {
      type: String,
      default: ''
    },
    is_valid_url: {
      type: Boolean,
      default: true
    },
    report_file_type: {
      type: String,
      default: 'HTML'
    },
    report_status: {
      type: String,
      default: 'crawled'
    },

    //# Báo cáo gốc từ nguồn
    bctt_net_revenue: {
      type: Number
    },
    bctt_cost_of_goods_sold: {
      type: Number
    },
    bctt_gross_profit: {
      type: Number
    },
    bctt_financial_income: {
      type: Number
    },
    bctt_financial_expense: {
      type: Number
    },
    bctt_selling_expense: {
      type: Number
    },
    bctt_admin_expense: {
      type: Number
    },
    bctt_net_operating_profit: {
      type: Number
    },
    bctt_other_profit: {
      type: Number
    },
    bctt_associate_jv_profit: {
      type: Number
    },
    bctt_profit_before_tax: {
      type: Number
    },
    bctt_profit_after_tax: {
      type: Number
    },
    bctt_parent_company_profit: {
      type: Number
    },
    bctt_basic_eps: {
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
    collection: 'factFinancialReportSources'
  }
);

FactFinancialReportSourceSchema.index({ stock_id: 1, report_period_id: 1, source_url: 1 }, { unique: true });

module.exports = mongoose.model('FactFinancialReportSource', FactFinancialReportSourceSchema);
