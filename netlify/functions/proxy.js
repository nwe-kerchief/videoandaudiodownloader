const { API_URL } = process.env;

exports.handler = async (event, context) => {
  try {
    const response = await fetch(API_URL, {
      method: event.httpMethod,
      headers: { 'Content-Type': 'application/json' },
      body: event.body
    });
    
    const data = await response.json();
    
    return {
      statusCode: 200,
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
