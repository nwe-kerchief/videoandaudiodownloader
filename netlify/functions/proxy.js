exports.handler = async (event, context) => {
  const API_URL = process.env.API_URL; // Hidden in environment variables
  
  try {
    const response = await fetch(API_URL, {
      method: event.httpMethod,
      headers: { 'Content-Type': 'application/json' },
      body: event.body
    });
    
    const data = await response.json();
    
    return {
      statusCode: 200,
      body: JSON.stringify(data)
    };
  } catch (error) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to fetch data' })
    };
  }
};
