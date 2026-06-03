const mongoose = require('mongoose');
const connectDB = require('../../config/database.config');

const run = async () => {
  await connectDB();
  const logsCol = mongoose.connection.db.collection('crawlLogs');
  const detailsCol = mongoose.connection.db.collection('crawlLogDetails');

  const latestLog = await logsCol.findOne({}, { sort: { started_at: -1 } });
  console.log('Latest Crawl Log:', latestLog);

  if (latestLog) {
    const details = await detailsCol.find({ crawl_log_id: latestLog._id }).toArray();
    console.log('Crawl Log Details:', details.map(d => ({
      symbol: d.symbol,
      data_type: d.data_type,
      status: d.status,
      message: d.message
    })));
  }

  await mongoose.connection.close();
  process.exit(0);
};

run();
