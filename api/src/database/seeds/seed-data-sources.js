const DimDataSource = require('../models/dim-data-source.model');

const seedDataSources = async () => {
  const sources = [
    {
      name: 'vnstock',
      provider_type: 'python_library',
      base_url: 'https://github.com/thinh-vu/vnstock',
      description: 'Thư viện Python mã nguồn mở để truy xuất dữ liệu chứng khoán Việt Nam',
      status: 'active'
    },
    {
      name: 'cafef',
      provider_type: 'crawler',
      base_url: 'https://cafef.vn',
      description: 'Trang tài chính CafeF - nguồn dữ liệu cổ phiếu và thị trường',
      status: 'active'
    },
    {
      name: 'ssi',
      provider_type: 'API',
      base_url: 'https://iboard.ssi.com.vn',
      description: 'SSI Securities - API dữ liệu thị trường chứng khoán',
      status: 'active'
    },
    {
      name: 'vndirect',
      provider_type: 'API',
      base_url: 'https://finfo-api.vndirect.com.vn',
      description: 'VNDIRECT Securities - API dữ liệu tài chính và cổ phiếu',
      status: 'active'
    },
    {
      name: 'hsx',
      provider_type: 'crawler',
      base_url: 'https://www.hsx.vn',
      description: 'Sàn HOSE - nguồn dữ liệu chính thức từ Sở Giao dịch Chứng khoán TP.HCM',
      status: 'active'
    }
  ];

  const seeded = [];
  for (const src of sources) {
    let exist = await DimDataSource.findOne({ name: src.name });
    if (!exist) {
      exist = await DimDataSource.create(src);
      console.log(`[Seed] Created data source: ${src.name}`);
    } else {
      await DimDataSource.findOneAndUpdate({ name: src.name }, {
        $set: {
          provider_type: src.provider_type,
          base_url: src.base_url,
          description: src.description,
          status: src.status
        }
      });
      exist = await DimDataSource.findOne({ name: src.name });
      console.log(`[Seed] Data source ${src.name} already exists — updated.`);
    }
    seeded.push(exist);
  }
  return seeded;
};

module.exports = seedDataSources;
