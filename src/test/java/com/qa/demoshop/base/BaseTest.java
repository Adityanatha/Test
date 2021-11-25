package com.qa.demoshop.base;

import java.util.Properties;

import org.openqa.selenium.WebDriver;
import org.testng.annotations.*;
import org.testng.asserts.SoftAssert;

import com.qa.demoshop.factory.DriverFactory;
import com.qa.demoshop.pages.AccountsPage;
import com.qa.demoshop.pages.LoginPage;
import com.qa.demoshop.pages.ProductInfoPage;
import com.qa.demoshop.pages.RegisterationPage;
import com.qa.demoshop.pages.ResultsPage;

public class BaseTest {

	public WebDriver driver;
	public Properties prop;
	public DriverFactory df;
	public LoginPage loginPage;
	public AccountsPage accPage;
	public ResultsPage resultPage;
	public ProductInfoPage productInfoPage;
	public RegisterationPage registerationPage;
	
	public SoftAssert softAssert;

	
	@Parameters({"browser", "browserversion"})
	@BeforeClass
	public void setUp(String browser, String browserVersion) {
		df = new DriverFactory();
		prop = df.initProp();
		
		if(browser!=null) {
			prop.setProperty("browser", browser);
			prop.setProperty("browserversion", browserVersion);
		}
		
		driver = df.initDriver(prop);
		loginPage = new LoginPage(driver);
		softAssert = new SoftAssert();
	}

	@AfterClass
	public void tearDown() {
		driver.quit();
	}

}
