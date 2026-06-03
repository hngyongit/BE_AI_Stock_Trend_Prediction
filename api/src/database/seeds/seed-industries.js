const DimIndustry = require('../models/dim-industry.model');

const seedIndustries = async () => {
  const industries = [
    {
      industry_name: 'Banking',
      sector_name: 'Financial Services',
      description: 'Ngân hàng thương mại và tổ chức tín dụng'
    },
    {
      industry_name: 'Insurance',
      sector_name: 'Financial Services',
      description: 'Bảo hiểm nhân thọ và phi nhân thọ'
    },
    {
      industry_name: 'Securities',
      sector_name: 'Financial Services',
      description: 'Công ty chứng khoán và quản lý quỹ'
    },
    {
      industry_name: 'Real Estate',
      sector_name: 'Real Estate',
      description: 'Bất động sản nhà ở và thương mại'
    },
    {
      industry_name: 'Construction',
      sector_name: 'Industrials',
      description: 'Xây dựng và vật liệu xây dựng'
    },
    {
      industry_name: 'Steel',
      sector_name: 'Materials',
      description: 'Sắt thép và kim loại'
    },
    {
      industry_name: 'Technology',
      sector_name: 'Information Technology',
      description: 'Công nghệ thông tin, phần mềm và viễn thông'
    },
    {
      industry_name: 'Consumer Goods',
      sector_name: 'Consumer Staples',
      description: 'Hàng tiêu dùng thiết yếu và bán lẻ'
    },
    {
      industry_name: 'Food & Beverage',
      sector_name: 'Consumer Staples',
      description: 'Thực phẩm, đồ uống và nông sản'
    },
    {
      industry_name: 'Energy',
      sector_name: 'Energy',
      description: 'Dầu khí, điện và năng lượng tái tạo'
    },
    {
      industry_name: 'Transportation',
      sector_name: 'Industrials',
      description: 'Vận tải biển, hàng không và logistics'
    },
    {
      industry_name: 'Healthcare',
      sector_name: 'Healthcare',
      description: 'Dược phẩm, y tế và thiết bị y tế'
    }
  ];

  const seeded = [];
  for (const ind of industries) {
    let exist = await DimIndustry.findOne({ industry_name: ind.industry_name });
    if (!exist) {
      exist = await DimIndustry.create(ind);
      console.log(`[Seed] Created industry: ${ind.industry_name}`);
    } else {
      await DimIndustry.findOneAndUpdate({ industry_name: ind.industry_name }, {
        $set: {
          sector_name: ind.sector_name,
          description: ind.description
        }
      });
      exist = await DimIndustry.findOne({ industry_name: ind.industry_name });
      console.log(`[Seed] Industry ${ind.industry_name} already exists — updated.`);
    }
    seeded.push(exist);
  }
  return seeded;
};

module.exports = seedIndustries;
