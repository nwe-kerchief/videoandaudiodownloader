const { API_URL } = process.env;

exports.handler = async (event, context) => {
  // Parse the data your frontend sent
  const { url, format } = JSON.parse(event.body);
  
  try {
    // Forward to your real API (hidden URL)
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, format })
    });
    
    const data = await response.json();
    
    return {
      statusCode: response.status,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    };
  } catch (error) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: error.message })
    };
  }
};
